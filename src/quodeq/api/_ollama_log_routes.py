"""Ollama log-stream route — SSE tail of ~/.ollama/logs/server.log."""
from __future__ import annotations

import os
import sys
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._sse_log_helpers import sse_tail_generator


def _ollama_log_path() -> Path | None:
    """Return the platform's Ollama server log path, or None if not present.

    macOS / Linux: ~/.ollama/logs/server.log
    Windows: %LOCALAPPDATA%/Ollama/server.log
    """
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if not local_app:
            return None
        return Path(local_app) / "Ollama" / "server.log"
    return Path.home() / ".ollama" / "logs" / "server.log"


# Ollama's server.log contains startup banners, model-load traces, and
# per-request entries from the Gin HTTP framework. The request lines (which
# show what quodeq is asking the model for) are the actionable signal; the
# rest is noise for debugging-the-runtime, not debugging-your-evaluation.
def _is_gin_line(line: str) -> bool:
    return "[GIN]" in line


def register_ollama_log_routes(app: Flask) -> None:
    """Register the /api/ollama/logs/stream SSE endpoint.

    Auth: inherits protection from the global before_request hook.
    """

    @app.get("/api/ollama/logs/stream")
    def stream_ollama_logs() -> Response | tuple[Response, int]:
        log_path = _ollama_log_path()
        if log_path is None or not log_path.exists():
            return (
                jsonify({
                    "error": "ollama log unavailable",
                    "code": "NOT_FOUND",
                    "help": "Could not locate the Ollama server log. Start the Ollama app or run `ollama serve`.",
                }),
                HTTPStatus.NOT_FOUND,
            )
        last_event_id = request.headers.get("Last-Event-ID", "")
        try:
            initial_offset = int(last_event_id) if last_event_id else 0
        except ValueError:
            initial_offset = 0

        resp = Response(
            sse_tail_generator(log_path, initial_offset, line_filter=_is_gin_line),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
