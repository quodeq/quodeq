"""HTTP surface for the embedded assistant (sessions, turns, SSE, actions)."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api._assistant_helpers import (
    build_tool_context,
    event_frames,
    get_repository,
    local_provider_busy,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.llm_bridge import get_provider_configs
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


def register_assistant_routes(app: Flask) -> None:
    @app.post("/api/assistant/sessions")
    def create_assistant_session():
        body = request.get_json(silent=True) or {}
        provider_cfg = _api_provider(str(body.get("provider", "")))
        if provider_cfg is None:
            return jsonify({"error": "unknown or unsupported provider"}), 400
        session_id = uuid.uuid4().hex
        # Plan 1 mapping: runDir → run_id column, repoRoot → project_uuid column.
        get_repository(app).create_session(
            session_id=session_id, provider=body["provider"],
            model=body.get("model"), project_uuid=body.get("repoRoot"),
            run_id=body.get("runDir"),
        )
        return jsonify({"sessionId": session_id}), 201

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
        provider_cfg = _api_provider(session["provider"]) or {}
        turn = TurnRequest(
            session_id=sid, text=text, ui_state=body.get("uiState"),
            api_base=body.get("apiBase") or provider_cfg.get("api_base", ""),
            api_key=body.get("apiKey"), provider=session["provider"],
            model=body.get("model") or session.get("model") or provider_cfg.get("model", ""),
        )
        tool_ctx = build_tool_context(app, session)

        def _worker():
            try:
                run_turn(turn, repository=repo, tool_ctx=tool_ctx)
            finally:
                with _running_lock:
                    _running_turns.discard(sid)

        threading.Thread(target=_worker, daemon=True).start()
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
            yield ":keepalive\n\n"
            for seq, frame in event_frames(repo, sid, after):
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
        result = service.import_from_file(action["payload"], force=False)
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
