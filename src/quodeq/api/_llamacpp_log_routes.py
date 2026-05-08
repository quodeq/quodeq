"""llama.cpp log-stream route — opt-in SSE tail of a user-pointed file.

Quodeq does not start ``llama-server``; the user does. So unlike the
Ollama log (which lives in a known location), the only way to surface
llama-server output in the dashboard is to have the user point us at a
log file via the ``LLAMACPP_LOG_FILE`` env var. If unset or missing,
the route returns 404 and the UI hides the console button.

Typical usage:

    llama-server -m model.gguf --port 8080 > /tmp/llama-server.log 2>&1
    LLAMACPP_LOG_FILE=/tmp/llama-server.log quodeq
"""
from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._sse_log_helpers import sse_tail_generator


def _llamacpp_log_path() -> Path | None:
    """Return the user-configured llama.cpp log path, or None."""
    override = os.environ.get("LLAMACPP_LOG_FILE")
    if not override:
        return None
    return Path(override)


def register_llamacpp_log_routes(app: Flask) -> None:
    """Register the /api/llamacpp/logs/{available,stream} endpoints.

    Auth: inherits protection from the global before_request hook.
    """

    @app.get("/api/llamacpp/logs/available")
    def llamacpp_logs_available() -> Response:
        """Tell the UI whether log streaming is configured.

        The console toggle in the llama.cpp settings tab is only shown
        when this returns ``{"available": true}``, since opening an SSE
        connection that immediately 404s would just produce a confusing
        red error pill.
        """
        log_path = _llamacpp_log_path()
        return jsonify({"available": bool(log_path and log_path.exists())})

    @app.get("/api/llamacpp/logs/stream")
    def stream_llamacpp_logs() -> Response | tuple[Response, int]:
        log_path = _llamacpp_log_path()
        if log_path is None or not log_path.exists():
            return (
                jsonify({
                    "error": "llamacpp log unavailable",
                    "code": "NOT_FOUND",
                    "help": (
                        "Set the LLAMACPP_LOG_FILE env var to a file llama-server is "
                        "writing to (for example: "
                        "`llama-server -m model.gguf --port 8080 > /tmp/llama-server.log 2>&1`, "
                        "then `LLAMACPP_LOG_FILE=/tmp/llama-server.log quodeq`)."
                    ),
                }),
                HTTPStatus.NOT_FOUND,
            )
        last_event_id = request.headers.get("Last-Event-ID", "")
        try:
            initial_offset = int(last_event_id) if last_event_id else 0
        except ValueError:
            initial_offset = 0

        resp = Response(
            sse_tail_generator(log_path, initial_offset),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
