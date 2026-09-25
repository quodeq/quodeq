"""Turn lifecycle routes for the embedded assistant: post message, stop, SSE
event stream.

Split out of assistant_routes.py. The provider lookup, the endpoint
resolver, the shared-clone gate and the turn/tool-context entry points are
injected by the registrar (``TurnGates``): they live in ``assistant_routes``
so tests patching "quodeq.api.assistant_routes.get_provider_configs" /
"...run_turn" / "...build_tool_context" keep working, and this module never
imports that facade.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._assistant_helpers import (
    SharedSourceUnavailable,
    event_frames,
    get_repository,
    local_provider_busy,
)
from quodeq.api._sse_log_helpers import sse_line
from quodeq.api.assistant_turn_state import AssistantTurnState, turn_state
from quodeq.api.helpers import json_error, optional_json_object_or_error
from quodeq.assistant.cancel import CancelToken
from quodeq.assistant.frame_type import FrameType
from quodeq.assistant.orchestrator import TurnRequest
from quodeq.assistant.tools import ToolContext
from quodeq.core.types.project_source import ProjectSource


@dataclass(frozen=True)
class TurnGates:
    """Facade entry points a turn needs, supplied by the registering facade."""

    api_provider: Callable[[str], dict | None]
    turn_endpoint: Callable[[str, dict, dict], tuple[str, str | None]]
    shared_source_error: Callable[[], tuple[Response, int] | None]
    run_turn: Callable[..., None]
    build_tool_context: Callable[[Flask, dict], ToolContext]


def _start_turn_worker(state: AssistantTurnState, turn: TurnRequest,
                       repo, tool_ctx, cancel: CancelToken,
                       run_turn: Callable[..., None]) -> None:
    """Run the turn on a daemon thread, freeing the session's turn slot when it
    ends however it ends. Takes *state* directly: the worker thread has no app
    context, so it cannot resolve current_app."""
    def _worker():
        try:
            run_turn(turn, repository=repo, tool_ctx=tool_ctx, cancel=cancel)
        finally:
            state.release_turn(turn.session_id)

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


_HEARTBEAT_IDLE_TICKS = 20  # ~5s at POLL_SECONDS; throttles the heartbeat DATA frame


def _sse_event_generator(repo, sid: str, after: int):
    # SSE comments (":keepalive") are invisible to EventSource — only
    # DATA frames fire onmessage and reset the browser's inactivity
    # timer. So on sustained idle (e.g. a slow local model still
    # cold-loading) we must periodically emit a real heartbeat DATA
    # frame, not just comments. Throttled to ~every _HEARTBEAT_IDLE_TICKS-th
    # idle tick (_HEARTBEAT_IDLE_TICKS * POLL_SECONDS == ~5s) so we don't
    # spam a data frame every 0.25s; cheap ":keepalive" comments fill the
    # gaps in between.
    yield ":keepalive\n\n"
    idle_ticks = 0
    for item in event_frames(repo, sid, after):
        if item is None:
            idle_ticks += 1
            if idle_ticks % _HEARTBEAT_IDLE_TICKS == 0:
                yield sse_line(json.dumps({"type": FrameType.HEARTBEAT}))
            else:
                yield ":keepalive\n\n"
        else:
            idle_ticks = 0
            seq, frame = item
            yield sse_line(json.dumps(frame, ensure_ascii=False), event_id=seq)


def _build_turn_request(sid: str, session: dict, body: dict, text: str,
                        gates: TurnGates) -> TurnRequest:
    """Resolve the provider endpoint and assemble the TurnRequest for *sid*."""
    provider_cfg = gates.api_provider(session["provider"]) or {}
    api_base, api_key = gates.turn_endpoint(session["provider"], body, provider_cfg)
    return TurnRequest(
        session_id=sid, text=text, ui_state=body.get("uiState"),
        api_base=api_base,
        api_key=api_key, provider=session["provider"],
        model=body.get("model") or session.get("model") or provider_cfg.get("model", ""),
        web_enabled=bool(body.get("webEnabled", False)),
        write_enabled=(bool(body.get("writeEnabled", False))
                       and (session.get("source") or ProjectSource.LOCAL) == ProjectSource.LOCAL),
    )


def _post_assistant_message(app: Flask, sid: str, gates: TurnGates):
    repo = get_repository(app)
    session = repo.get_session(sid)
    if session is None:
        return json_error("unknown session", 404, "UNKNOWN_SESSION")
    body = optional_json_object_or_error("INVALID_PARAM")
    if not isinstance(body, dict):
        return jsonify(body[0]), body[1]
    text = str(body.get("text", "")).strip()
    if not text:
        return json_error("text required", 400, "MISSING_PARAM")
    if local_provider_busy(session["provider"]):
        return json_error("model busy with analysis", 409, "PROVIDER_BUSY")
    if (session.get("source") or ProjectSource.LOCAL) == ProjectSource.SHARED:
        shared_error = gates.shared_source_error()
        if shared_error is not None:
            return shared_error
    state = turn_state(app)
    cancel = state.claim_turn(sid)
    if cancel is None:
        return json_error("a turn is already running", 409, "TURN_IN_PROGRESS")
    # Everything from here through Thread.start() must free the slot on
    # failure — otherwise an exception (e.g. build_tool_context blowing
    # up) leaves `sid` claimed forever and every future POST to this
    # session 409s permanently.
    try:
        turn = _build_turn_request(sid, session, body, text, gates)
        tool_ctx = gates.build_tool_context(app, session)
        _start_turn_worker(state, turn, repo, tool_ctx, cancel, gates.run_turn)
    except SharedSourceUnavailable:
        # Race between the pre-check above and this build_tool_context
        # call. Constant body, not str(exc): the pre-check already
        # reported the specific reason; this is just the narrow window
        # where the shared clone changed state in between.
        state.release_turn(sid)
        return jsonify({"error": "shared repository unavailable", "code": "SHARED_REPO_UNAVAILABLE"}), 409
    except Exception:
        state.release_turn(sid)
        raise
    return jsonify({"accepted": True}), 202


def _stop_assistant_turn(app: Flask, sid: str):
    if get_repository(app).get_session(sid) is None:
        return json_error("unknown session", 404, "UNKNOWN_SESSION")
    token = turn_state(app).cancel_token(sid)
    if token is None:
        return json_error("no turn running", 409, "NO_TURN_RUNNING")
    # Fire outside the lock: cancel() runs kill hooks (proc-tree kill /
    # client close) that must not serialize other sessions' turn claims.
    token.cancel()
    # 202: the turn thread still has to unwind; the SSE `stopped` frame is
    # the authoritative end-of-turn signal for the UI.
    return jsonify({"stopping": True}), 202


def _assistant_events(app: Flask, sid: str):
    repo = get_repository(app)
    if repo.get_session(sid) is None:
        return json_error("unknown session", 404, "UNKNOWN_SESSION")
    raw = request.headers.get("Last-Event-ID") or request.args.get("after", "0")
    try:
        after = int(raw)
    except ValueError:
        after = 0

    state = turn_state(app)
    if not state.try_open_sse_stream():
        return json_error("too many open event streams", 429, "TOO_MANY_STREAMS")

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


def register_assistant_turn_routes(app: Flask, gates: TurnGates) -> None:
    """Bind the turn routes: post message, stop, SSE event stream."""
    @app.post("/api/assistant/sessions/<sid>/messages")
    def post_assistant_message(sid: str):
        return _post_assistant_message(app, sid, gates)

    @app.post("/api/assistant/sessions/<sid>/stop")
    def stop_assistant_turn(sid: str):
        return _stop_assistant_turn(app, sid)

    @app.get("/api/assistant/sessions/<sid>/events")
    def assistant_events(sid: str):
        return _assistant_events(app, sid)
