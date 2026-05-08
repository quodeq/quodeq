"""llama.cpp log-stream route — SSE tail of a llama-server log file.

Quodeq does not start ``llama-server``; the user does. So unlike the
Ollama log (which lives in a known location), there is no log file
unless the user redirects ``llama-server``'s stdout to one. We resolve
a path in this order:

    1. ``LLAMACPP_LOG_FILE`` env var (explicit override)
    2. Platform-standard fallback paths (see ``_DEFAULT_LOG_PATHS``)

If neither produces an existing file, the route returns 404 and the UI
hides the console button. Recommended launch:

    # macOS
    llama-server -m model.gguf --port 8080 > ~/Library/Logs/llama-server.log 2>&1

    # Linux
    llama-server -m model.gguf --port 8080 > ~/.local/state/llama-server.log 2>&1
"""
from __future__ import annotations

import os
import sys
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._sse_log_helpers import sse_tail_generator


def _default_log_paths() -> list[Path]:
    """Return platform-standard locations to probe when the env var is unset.

    First match wins. We only return paths the user is likely to have
    written to themselves (Library/Logs on macOS, XDG state dir on
    Linux, LocalAppData on Windows) plus ``/tmp/llama-server.log`` as
    the lowest-friction default that "just works" if they redirected
    output to ``/tmp``.
    """
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.append(home / "Library" / "Logs" / "llama-server.log")
    elif sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "llama.cpp" / "server.log")
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME") or str(home / ".local" / "state")
        candidates.append(Path(xdg_state) / "llama-server.log")
    candidates.append(Path("/tmp/llama-server.log"))
    return candidates


def _llamacpp_log_path() -> Path | None:
    """Resolve a usable log path, or None if no candidate file exists."""
    override = os.environ.get("LLAMACPP_LOG_FILE")
    if override:
        # Honor an explicit override even if the file doesn't exist yet —
        # llama-server might create it on next launch and the UI's
        # availability poll will pick it up then.
        return Path(override)
    for candidate in _default_log_paths():
        if candidate.exists():
            return candidate
    return None


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
                        "Could not locate a llama-server log file. Either redirect "
                        "llama-server's output to a standard path (e.g. on macOS: "
                        "`llama-server -m model.gguf --port 8080 > ~/Library/Logs/llama-server.log 2>&1`) "
                        "or set the LLAMACPP_LOG_FILE env var to its location."
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
