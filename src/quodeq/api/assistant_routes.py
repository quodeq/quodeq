"""HTTP surface for the embedded assistant (sessions, turns, SSE, actions)."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api import _assistant_helpers
from quodeq.api._assistant_helpers import (
    _LOCAL_PROVIDERS as _FIXED_ENDPOINT_PROVIDERS,
    build_tool_context,
    event_frames,
    get_repository,
    local_provider_busy,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.assistant import get_provider_configs
from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.assistant.skills import RESERVED_COMMANDS, load_skills
from quodeq.assistant.tools._actions import ACTION_DESCRIPTIONS, ACTION_TYPES
from quodeq.services.standards import StandardsService

_running_turns: set[str] = set()
_running_lock = threading.Lock()


def _api_provider(provider_id: str) -> dict | None:
    # get_provider_configs() returns dict[str, dict] keyed by provider id
    # (see src/quodeq/analysis/_provider_cache.py:67 and the top-level keys
    # of data/config/ai_providers.json) — not the {"providers": [...]} list
    # shape the original plan assumed.
    cfg = get_provider_configs().get(provider_id)
    if cfg is None or cfg.get("type") != "api":
        return None
    return cfg


def _known_provider(provider_id: str) -> dict | None:
    """Any catalog entry regardless of type (api or cli); unknown ids are None."""
    return get_provider_configs().get(provider_id)


def register_assistant_routes(app: Flask) -> None:
    @app.post("/api/assistant/sessions")
    def create_assistant_session():
        body = request.get_json(silent=True) or {}
        provider_cfg = _known_provider(str(body.get("provider", "")))
        if provider_cfg is None:
            return jsonify({"error": "unknown or unsupported provider"}), 400
        session_id = uuid.uuid4().hex
        # Plan 1 mapping: runDir → run_id column, repoRoot → project_uuid column.
        # Client-supplied runDir/repoRoot are NOT honored: they'd flow to the
        # MCP subprocess's --run-dir/--repo-root with no path jail, giving a
        # remote API-key caller arbitrary server-side file access. The real UI
        # never sends these — it sends {projectId, runId} and the server
        # resolves run_dir/repo_root itself via the jailed resolver.
        run_dir, repo_root = None, None
        # Only bind a single run when the UI selected a SPECIFIC run. On the
        # overview it sends projectId with no runId → the session stays
        # run-unscoped and the detail tools read the accumulated
        # (per-dimension-latest) composition from project_id + reports_dir.
        if body.get("projectId") and body.get("runId"):
            run_dir, repo_root = _assistant_helpers.resolve_run_location(
                str(body["projectId"]), str(body["runId"]),
            )
        elif body.get("projectId"):
            # The repo root is a project-level fact; without it, run-unscoped
            # sessions (the app's default state) cannot read code at all.
            repo_root = _assistant_helpers.resolve_repo_root(str(body["projectId"]))
        project_id = body.get("projectId")
        get_repository(app).create_session(
            session_id=session_id, provider=body["provider"],
            model=body.get("model"), project_uuid=repo_root,
            run_id=run_dir,
            project_id=str(project_id) if project_id else None,
        )
        return jsonify({"sessionId": session_id}), 201

    @app.get("/api/assistant/skills")
    def get_assistant_catalog():
        # Static catalog for the drawer's welcome panel, autocomplete, and
        # /help /skills /actions meta-commands. Read-only, no session needed.
        return jsonify({
            "commands": [{"name": n, "description": d} for n, d in RESERVED_COMMANDS],
            "skills": [
                {"name": s.name, "description": s.description,
                 "argumentHint": s.argument_hint, "views": list(s.views)}
                for s in load_skills().values()
            ],
            "actions": [
                {"type": t, "description": ACTION_DESCRIPTIONS.get(t, "")}
                for t in sorted(ACTION_TYPES)
            ],
        })

    @app.post("/api/assistant/sessions/<sid>/messages")
    def post_assistant_message(sid: str):
        repo = get_repository(app)
        session = repo.get_session(sid)
        if session is None:
            return jsonify({"error": "unknown session"}), 404
        body = request.get_json(silent=True) or {}
        text = str(body.get("text", "")).strip()
        if not text:
            return jsonify({"error": "text required"}), 400
        if local_provider_busy(session["provider"]):
            return jsonify({"error": "model busy with analysis"}), 409
        with _running_lock:
            if sid in _running_turns:
                return jsonify({"error": "a turn is already running"}), 409
            _running_turns.add(sid)
        # Everything from here through Thread.start() must free the slot on
        # failure — otherwise an exception (e.g. build_tool_context blowing
        # up) leaves `sid` in `_running_turns` forever and every future POST
        # to this session 409s permanently.
        try:
            provider_cfg = _api_provider(session["provider"]) or {}
            catalog_cfg = _known_provider(session["provider"])
            # CLI providers (claude/codex/gemini) have no HTTP endpoint to pin or
            # override — the orchestrator's run_turn dispatches them internally
            # (spawning the CLI subprocess), so apiBase/apiKey are meaningless
            # here and left unset.
            if catalog_cfg is not None and catalog_cfg.get("type") == "cli":
                api_base = ""
                api_key = None
            # api_base is ALWAYS the server's catalog value, never the request
            # body: a caller-supplied apiBase would redirect the turn (and its
            # tool calls) at an arbitrary host (SSRF into internal services /
            # cloud metadata). The UI never sends one — provider endpoints live
            # in ai_providers.json. api_key may still come from the request for
            # genuinely caller-defined providers (custom/openrouter) — it's a
            # credential the caller supplies, not a fetch target — falling back
            # to server config; fixed-endpoint local providers need none.
            elif session["provider"] in _FIXED_ENDPOINT_PROVIDERS:
                api_base = provider_cfg.get("api_base", "")
                api_key = None
            else:
                api_base = provider_cfg.get("api_base", "")
                api_key = body.get("apiKey") or provider_cfg.get("api_key")
            turn = TurnRequest(
                session_id=sid, text=text, ui_state=body.get("uiState"),
                api_base=api_base,
                api_key=api_key, provider=session["provider"],
                model=body.get("model") or session.get("model") or provider_cfg.get("model", ""),
                web_enabled=bool(body.get("webEnabled", False)),
            )
            tool_ctx = build_tool_context(app, session)

            def _worker():
                try:
                    run_turn(turn, repository=repo, tool_ctx=tool_ctx)
                finally:
                    with _running_lock:
                        _running_turns.discard(sid)

            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            with _running_lock:
                _running_turns.discard(sid)
            raise
        return jsonify({"accepted": True}), 202

    @app.get("/api/assistant/sessions/<sid>/events")
    def assistant_events(sid: str):
        repo = get_repository(app)
        if repo.get_session(sid) is None:
            return jsonify({"error": "unknown session"}), 404
        raw = request.headers.get("Last-Event-ID") or request.args.get("after", "0")
        try:
            after = int(raw)
        except ValueError:
            after = 0

        def _generate():
            # SSE comments (":keepalive") are invisible to EventSource — only
            # DATA frames fire onmessage and reset the browser's inactivity
            # timer. So on sustained idle (e.g. a slow local model still
            # cold-loading) we must periodically emit a real heartbeat DATA
            # frame, not just comments. Throttled to ~every 20th idle tick
            # (20 * _POLL_SECONDS == ~5s) so we don't spam a data frame every
            # 0.25s; cheap ":keepalive" comments fill the gaps in between.
            yield ":keepalive\n\n"
            idle_ticks = 0
            for item in event_frames(repo, sid, after):
                if item is None:
                    idle_ticks += 1
                    if idle_ticks % 20 == 0:
                        yield sse_line(json.dumps({"type": "heartbeat"}))
                    else:
                        yield ":keepalive\n\n"
                else:
                    idle_ticks = 0
                    seq, frame = item
                    yield sse_line(json.dumps(frame, ensure_ascii=False), event_id=seq)

        resp = Response(_generate(), mimetype="text/event-stream")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        action = repo.get_action(action_id)
        if action is None:
            return jsonify({"error": "unknown action"}), 404
        if action["status"] != "drafted":
            return jsonify({"error": f"action already {action['status']}"}), 409
        service = StandardsService(
            Path(current_app.config["STANDARDS_EVALUATORS_DIR"]),
            Path(current_app.config["STANDARDS_COMPILED_DIR"]),
            Path(current_app.config["STANDARDS_DIMENSIONS_FILE"]),
        )
        # StandardsService.import_from_file returns {"status": "conflict"|"imported", ...}
        # (see src/quodeq/services/_standards_crud.py:86-105) — not a boolean "conflict"
        # key the original plan assumed.
        try:
            result = service.import_from_file(action["payload"], force=False)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if result.get("status") == "conflict":
            return jsonify({"error": "standard id already exists"}), 409
        repo.set_action_status(action_id, "applied")
        return jsonify({"applied": True, "result": result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        if repo.get_action(action_id) is None:
            return jsonify({"error": "unknown action"}), 404
        repo.set_action_status(action_id, "rejected")
        return jsonify({"status": "rejected"}), 200
