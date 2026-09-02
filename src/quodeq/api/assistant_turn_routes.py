"""Turn lifecycle routes for the embedded assistant: post message, stop, SSE
event stream.

Split out of assistant_routes.py (Task 10). ``_api_provider``,
``_turn_endpoint``, ``run_turn``, and ``build_tool_context`` are looked up on
the ``assistant_routes`` facade at call time (rather than imported directly
here) so that tests patching "quodeq.api.assistant_routes.get_provider_
configs" / "...run_turn" / "...build_tool_context" keep working after the
split.
"""
from __future__ import annotations

import json
import threading

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import (
    SharedSourceUnavailable,
    event_frames,
    get_repository,
    local_provider_busy,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.api.assistant_turn_state import AssistantTurnState, _turn_state
from quodeq.assistant.cancel import CancelToken
from quodeq.assistant.orchestrator import TurnRequest
from quodeq.services.score_cache import score_cache_path_override


def _start_turn_worker(state: AssistantTurnState, sid: str, turn: TurnRequest,
                       repo, tool_ctx, cancel: CancelToken) -> None:
    """Run the turn on a daemon thread, freeing the session's turn slot when it
    ends however it ends. Takes *state* directly: the worker thread has no app
    context, so it cannot resolve current_app."""
    def _worker():
        from quodeq.api import assistant_routes as _assistant_routes  # noqa: PLC0415 — deferred: see module docstring
        try:
            if tool_ctx.score_cache_path is not None:
                with score_cache_path_override(tool_ctx.score_cache_path):
                    _assistant_routes.run_turn(turn, repository=repo, tool_ctx=tool_ctx, cancel=cancel)
            else:
                _assistant_routes.run_turn(turn, repository=repo, tool_ctx=tool_ctx, cancel=cancel)
        finally:
            state.release_turn(sid)

    threading.Thread(target=_worker, daemon=True).start()


def _sse_release_guard(state: AssistantTurnState):
    """Idempotent release-once wrapper around ``state.close_sse_stream()``.

    Returns a callable that runs from both the generator's ``finally`` and
    the response's on-close callback (the callback covers the case where the
    client drops before the generator is ever started, in which case a
    generator finally never executes).
    """
    released = False
    guard = threading.Lock()

    def _release():
        nonlocal released
        with guard:
            if released:
                return
            released = True
        state.close_sse_stream()

    return _release


def _sse_event_generator(repo, sid: str, after: int):
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


def register_assistant_turn_routes(app: Flask) -> None:
    @app.post("/api/assistant/sessions/<sid>/messages")
    def post_assistant_message(sid: str):
        from quodeq.api import assistant_routes as _assistant_routes  # noqa: PLC0415 — deferred: see module docstring
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
            provider_cfg = _assistant_routes._api_provider(session["provider"]) or {}
            api_base, api_key = _assistant_routes._turn_endpoint(
                session["provider"], body, provider_cfg)
            turn = TurnRequest(
                session_id=sid, text=text, ui_state=body.get("uiState"),
                api_base=api_base,
                api_key=api_key, provider=session["provider"],
                model=body.get("model") or session.get("model") or provider_cfg.get("model", ""),
                web_enabled=bool(body.get("webEnabled", False)),
                write_enabled=(bool(body.get("writeEnabled", False))
                               and (session.get("source") or "local") == "local"),
            )
            tool_ctx = _assistant_routes.build_tool_context(app, session)
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

        release = _sse_release_guard(state)

        def _generate():
            try:
                yield from _sse_event_generator(repo, sid, after)
            finally:
                release()

        resp = Response(_generate(), mimetype="text/event-stream")
        resp.call_on_close(release)
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
