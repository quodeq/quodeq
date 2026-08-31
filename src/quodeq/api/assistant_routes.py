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
    SharedSourceUnavailable,
    build_action_context,
    build_tool_context,
    event_frames,
    get_repository,
    local_provider_busy,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.api.assistant_workspace_routes import register_assistant_workspace_routes
from quodeq.assistant import get_provider_configs
from quodeq.assistant.apply_action import apply_drafted_action
from quodeq.assistant.cancel import CancelToken
from quodeq.assistant.orchestrator import TurnRequest, run_turn, write_safe_provider
from quodeq.assistant.skills import RESERVED_COMMANDS, load_skills
from quodeq.assistant.tools._actions import ACTION_DESCRIPTIONS, ACTION_TYPES
from quodeq.services.score_cache import score_cache_path_override
from quodeq.services.shared_repo import read_state
from quodeq.services.shared_settings import read_settings

# Each open assistant SSE stream pins a server worker thread for its whole
# lifetime, and the global rate limiter exempts GETs — without a cap an
# authenticated caller can exhaust every worker with idle streams. 16 is
# generous for the real UI (one stream per open drawer/tab).
_MAX_SSE_STREAMS = 16


class AssistantTurnState:
    """Per-app registry of running turns, cancel tokens, and open SSE streams.

    One instance per Flask app (``app.extensions["assistant_turns"]``,
    created in ``create_app``) so two apps in one process — or two tests —
    never share turn slots. Lock granularity matches the former module
    globals: one lock guards the turn/token registry, another the SSE
    stream counter.
    """

    def __init__(self, max_sse_streams: int = _MAX_SSE_STREAMS) -> None:
        self._running_turns: set[str] = set()
        # Cancel token per session with a /messages turn in flight; the /stop
        # route fires it. Workspace actions (apply/pr) claim the turn slot too
        # but are not stoppable, so they never appear here.
        self._cancel_tokens: dict[str, CancelToken] = {}
        self._running_lock = threading.Lock()
        self._max_sse_streams = max_sse_streams
        self._open_sse_streams = 0
        self._sse_lock = threading.Lock()

    def try_claim_turn(self, sid: str) -> bool:
        """Atomically claim the per-session turn slot for a workspace action
        so a concurrent /messages turn (or another apply/pr) 409s instead of
        racing the same worktree. Returns False if already claimed."""
        with self._running_lock:
            if sid in self._running_turns:
                return False
            self._running_turns.add(sid)
            return True

    def claim_turn(self, sid: str) -> CancelToken | None:
        """Claim the turn slot for a /messages turn and mint its cancel token
        in one atomic step. Returns None when the slot is already claimed."""
        with self._running_lock:
            if sid in self._running_turns:
                return None
            self._running_turns.add(sid)
            token = self._cancel_tokens[sid] = CancelToken()
            return token

    def release_turn(self, sid: str) -> None:
        """Free the per-session turn slot and drop the turn's cancel token.

        Workspace actions never register a token, so the pop is a no-op for
        them; the slot is exclusive, so it can only ever drop this turn's own
        token."""
        with self._running_lock:
            self._running_turns.discard(sid)
            self._cancel_tokens.pop(sid, None)

    def is_turn_claimed(self, sid: str) -> bool:
        with self._running_lock:
            return sid in self._running_turns

    def cancel_token(self, sid: str) -> CancelToken | None:
        with self._running_lock:
            return self._cancel_tokens.get(sid)

    def try_open_sse_stream(self) -> bool:
        """Take one SSE slot; False when the cap is reached (caller 429s)."""
        with self._sse_lock:
            if self._open_sse_streams >= self._max_sse_streams:
                return False
            self._open_sse_streams += 1
            return True

    def close_sse_stream(self) -> None:
        with self._sse_lock:
            self._open_sse_streams -= 1

    @property
    def open_sse_streams(self) -> int:
        with self._sse_lock:
            return self._open_sse_streams


def _turn_state(app: Flask) -> AssistantTurnState:
    """The app's turn registry. ``create_app`` instantiates it; setdefault
    keeps bare test apps (register_assistant_routes on a plain Flask) working."""
    return app.extensions.setdefault("assistant_turns", AssistantTurnState())


def _try_claim_turn(sid: str) -> bool:
    """Request-context shim for the workspace routes (see AssistantTurnState)."""
    return _turn_state(current_app).try_claim_turn(sid)


def _release_turn(sid: str) -> None:
    """Request-context shim for the workspace routes (see AssistantTurnState)."""
    _turn_state(current_app).release_turn(sid)


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


def _shared_source_error() -> tuple[Response, int] | None:
    """The shared-clone gate for a new session: the 409 body when no shared
    repository is configured or its local clone state is unusable, else None."""
    settings = read_settings()
    if not settings.url:
        return jsonify({"error": "no shared repository configured"}), 409
    state = read_state(settings.url)
    if state not in ("ok", "empty"):
        return jsonify({"error": f"shared repository unavailable: {state}"}), 409
    return None


def _resolve_session_scope(source: str, body: dict) -> tuple[str | None, str | None, str]:
    """``(run_dir, repo_root, repo_reason)`` for a new session.

    Plan 1 mapping: runDir → run_id column, repoRoot → project_uuid column.
    Client-supplied runDir/repoRoot are NOT honored: they'd flow to the MCP
    subprocess's --run-dir/--repo-root with no path jail, giving a remote
    API-key caller arbitrary server-side file access. The real UI never sends
    these — it sends {projectId, runId} and the server resolves
    run_dir/repo_root itself via the jailed resolver.

    Three shapes:
    - shared: never attaches a repo (the clone has no working copy); data reads
      resolve against the clone's evaluations root in build_tool_context.
    - local + specific runId: binds that one run.
    - local overview (projectId, no runId): stays run-unscoped, so the detail
      tools read the accumulated (per-dimension-latest) composition from
      project_id + reports_dir.
    """
    project_id = body.get("projectId")
    if source == "shared":
        run_dir = None
        if project_id and body.get("runId"):
            run_dir = _assistant_helpers.resolve_shared_run_location(
                str(project_id), str(body["runId"]))
        return run_dir, None, "online_project"
    if not project_id:
        return None, None, "no_project"
    repo_root, repo_reason = _assistant_helpers.repo_attach_info(str(project_id))
    run_dir = None
    if body.get("runId"):
        run_dir, _ = _assistant_helpers.resolve_run_location(
            str(project_id), str(body["runId"]),
        )
    return run_dir, repo_root, repo_reason


def _turn_endpoint(provider: str, body: dict, provider_cfg: dict) -> tuple[str, str | None]:
    """``(api_base, api_key)`` for a turn — the trust boundary for both.

    api_base is ALWAYS the server's catalog value, never the request body: a
    caller-supplied apiBase would redirect the turn (and its tool calls) at an
    arbitrary host (SSRF into internal services / cloud metadata). The UI never
    sends one — provider endpoints live in ai_providers.json. api_key may still
    come from the request for genuinely caller-defined providers
    (custom/openrouter) — it's a credential the caller supplies, not a fetch
    target — falling back to server config; fixed-endpoint local providers need
    none.
    """
    catalog_cfg = _known_provider(provider)
    # CLI providers (claude/codex/gemini) have no HTTP endpoint to pin or
    # override — the orchestrator's run_turn dispatches them internally
    # (spawning the CLI subprocess), so apiBase/apiKey are meaningless here and
    # left unset.
    if catalog_cfg is not None and catalog_cfg.get("type") == "cli":
        return "", None
    if provider in _FIXED_ENDPOINT_PROVIDERS:
        return provider_cfg.get("api_base", ""), None
    return provider_cfg.get("api_base", ""), body.get("apiKey") or provider_cfg.get("api_key")


def _start_turn_worker(state: AssistantTurnState, sid: str, turn: TurnRequest,
                       repo, tool_ctx, cancel: CancelToken) -> None:
    """Run the turn on a daemon thread, freeing the session's turn slot when it
    ends however it ends. Takes *state* directly: the worker thread has no app
    context, so it cannot resolve current_app."""
    def _worker():
        try:
            if tool_ctx.score_cache_path is not None:
                with score_cache_path_override(tool_ctx.score_cache_path):
                    run_turn(turn, repository=repo, tool_ctx=tool_ctx, cancel=cancel)
            else:
                run_turn(turn, repository=repo, tool_ctx=tool_ctx, cancel=cancel)
        finally:
            state.release_turn(sid)

    threading.Thread(target=_worker, daemon=True).start()


def register_assistant_routes(app: Flask) -> None:
    _turn_state(app)  # ensure the registry exists even on bare test apps
    register_assistant_workspace_routes(app)

    @app.post("/api/assistant/sessions")
    def create_assistant_session():
        # First assistant request of the process: reap leaked worktrees +
        # prune stale sessions before minting a new one (one-shot, best-effort).
        _assistant_helpers.run_assistant_hygiene(app)
        body = request.get_json(silent=True) or {}
        provider_cfg = _known_provider(str(body.get("provider", "")))
        if provider_cfg is None:
            return jsonify({"error": "unknown or unsupported provider"}), 400
        source = str(body.get("source") or "local")
        if source not in ("local", "shared"):
            return jsonify({"error": "invalid source"}), 400
        if source == "shared":
            shared_error = _shared_source_error()
            if shared_error is not None:
                return shared_error
        session_id = uuid.uuid4().hex
        run_dir, repo_root, repo_reason = _resolve_session_scope(source, body)
        project_id = body.get("projectId")
        get_repository(app).create_session(
            session_id=session_id, provider=body["provider"],
            model=body.get("model"), project_uuid=repo_root,
            run_id=run_dir,
            project_id=str(project_id) if project_id else None,
            source=source,
        )
        write_available = (source == "local"
                           and bool(repo_root)
                           and (Path(repo_root) / ".git").exists()
                           and write_safe_provider(str(body["provider"])))
        return jsonify({"sessionId": session_id,
                        "repoAttached": repo_root is not None,
                        "repoReason": repo_reason,
                        "readOnly": source == "shared",
                        "writeAvailable": write_available}), 201

    @app.get("/api/assistant/skills")
    def get_assistant_catalog():
        # Static catalog for the drawer's welcome panel, autocomplete, and
        # /help /skills /actions meta-commands. Read-only, no session needed.
        return jsonify({
            "commands": [{"name": n, "description": d} for n, d in RESERVED_COMMANDS],
            "skills": [
                {"name": s.name, "description": s.description,
                 "argumentHint": s.argument_hint, "views": list(s.views),
                 "requiresWrite": s.requires_write}
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
        state = _turn_state(app)
        cancel = state.claim_turn(sid)
        if cancel is None:
            return jsonify({"error": "a turn is already running"}), 409
        # Everything from here through Thread.start() must free the slot on
        # failure — otherwise an exception (e.g. build_tool_context blowing
        # up) leaves `sid` claimed forever and every future POST to this
        # session 409s permanently.
        try:
            provider_cfg = _api_provider(session["provider"]) or {}
            api_base, api_key = _turn_endpoint(session["provider"], body, provider_cfg)
            turn = TurnRequest(
                session_id=sid, text=text, ui_state=body.get("uiState"),
                api_base=api_base,
                api_key=api_key, provider=session["provider"],
                model=body.get("model") or session.get("model") or provider_cfg.get("model", ""),
                web_enabled=bool(body.get("webEnabled", False)),
                write_enabled=(bool(body.get("writeEnabled", False))
                               and (session.get("source") or "local") == "local"),
            )
            tool_ctx = build_tool_context(app, session)
            _start_turn_worker(state, sid, turn, repo, tool_ctx, cancel)
        except SharedSourceUnavailable as exc:
            state.release_turn(sid)
            return jsonify({"error": str(exc)}), 409
        except Exception:
            state.release_turn(sid)
            raise
        return jsonify({"accepted": True}), 202

    @app.post("/api/assistant/sessions/<sid>/stop")
    def stop_assistant_turn(sid: str):
        if get_repository(app).get_session(sid) is None:
            return jsonify({"error": "unknown session"}), 404
        token = _turn_state(app).cancel_token(sid)
        if token is None:
            return jsonify({"error": "no turn running"}), 409
        # Fire outside the lock: cancel() runs kill hooks (proc-tree kill /
        # client close) that must not serialize other sessions' turn claims.
        token.cancel()
        # 202: the turn thread still has to unwind; the SSE `stopped` frame is
        # the authoritative end-of-turn signal for the UI.
        return jsonify({"stopping": True}), 202

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

        state = _turn_state(app)
        if not state.try_open_sse_stream():
            return jsonify({"error": "too many open event streams"}), 429

        released = False
        release_guard = threading.Lock()

        def _release_stream():
            # Idempotent: runs from both the generator's finally and the
            # response's on-close callback (the callback covers the case where
            # the client drops before the generator is ever started, in which
            # case a generator finally never executes).
            nonlocal released
            with release_guard:
                if released:
                    return
                released = True
            state.close_sse_stream()

        def _generate():
            # SSE comments (":keepalive") are invisible to EventSource — only
            # DATA frames fire onmessage and reset the browser's inactivity
            # timer. So on sustained idle (e.g. a slow local model still
            # cold-loading) we must periodically emit a real heartbeat DATA
            # frame, not just comments. Throttled to ~every 20th idle tick
            # (20 * _POLL_SECONDS == ~5s) so we don't spam a data frame every
            # 0.25s; cheap ":keepalive" comments fill the gaps in between.
            try:
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
            finally:
                _release_stream()

        resp = Response(_generate(), mimetype="text/event-stream")
        resp.call_on_close(_release_stream)
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    @app.post("/api/assistant/actions/<action_id>/apply")
    def apply_assistant_action(action_id: str):
        repo = get_repository(app)
        outcome = apply_drafted_action(repo, action_id, build_action_context(current_app))
        if outcome.kind == "unknown_action":
            return jsonify({"error": "unknown action"}), 404
        if outcome.kind == "read_only":
            return jsonify({"error": "read-only session"}), 403
        if outcome.kind == "already":
            return jsonify({"error": f"action already {outcome.detail}"}), 409
        if outcome.kind == "unsupported":
            return jsonify({"error": "unsupported action type"}), 400
        if outcome.kind == "invalid":
            return jsonify({"error": outcome.detail}), 400
        if outcome.kind == "conflict":
            return jsonify({"error": outcome.detail}), 409
        return jsonify({"applied": True, "result": outcome.result}), 200

    @app.post("/api/assistant/actions/<action_id>/reject")
    def reject_assistant_action(action_id: str):
        repo = get_repository(app)
        action = repo.get_action(action_id)
        if action is None:
            return jsonify({"error": "unknown action"}), 404
        owner = repo.get_session(action["session_id"])
        if owner is not None and (owner.get("source") or "local") == "shared":
            # Defense in depth: read-only sessions never draft actions
            # (draft_action is not registered), so nothing legitimate reaches
            # here. Refuse rather than mutate the local store under a shared
            # project id.
            return jsonify({"error": "read-only session"}), 403
        # Same replay guard as apply, made atomic: an applied action must
        # not flip to rejected on a stale card click, SSE replay, or a race
        # with a concurrent apply. The compare-and-set wins at most once.
        if not repo.set_action_status(action_id, "rejected", expected="drafted"):
            fresh = repo.get_action(action_id)
            state = fresh["status"] if fresh else "gone"
            return jsonify({"error": f"action already {state}"}), 409
        return jsonify({"status": "rejected"}), 200
