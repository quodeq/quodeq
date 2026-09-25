"""Log-console routes for a local model provider (Ollama, llama.cpp).

Each provider only differs in where its server log lives, what help text the
404 carries, how its log is tailed (which lines the console shows), and
whether the UI asks up front if a log exists. ``ProviderLog`` carries those differences; the routes are
the same for every provider:

- ``GET /api/<name>/logs/stream``: SSE tail of the log, resumable through
  ``Last-Event-ID`` (a byte offset), or 404 when there is no log file.
- ``GET /api/<name>/logs/available`` (only with ``availability_route``):
  ``{"available": bool}``, so the UI hides the console button instead of
  opening a stream that would 404.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_NOT_FOUND
from quodeq.api._sse_log_helpers import event_stream_response, initial_offset, sse_tail_generator


@dataclass(frozen=True)
class ProviderLog:
    """What one provider's log console needs.

    *log_path* is called as ``log_path(env=env)`` on every request and returns
    the log file, or None when there is nowhere to look. *tail* turns the log
    and a starting byte offset into SSE frames.
    """

    name: str
    log_path: Callable[..., Path | None]
    help: str
    tail: Callable[[Path, int], Iterable[str]] = sse_tail_generator
    availability_route: bool = False


def _existing_log(log: ProviderLog, env: Mapping[str, str] | None) -> Path | None:
    path = log.log_path(env=env)
    return path if path is not None and path.exists() else None


def register_provider_log_routes(
    app: Flask, log: ProviderLog, env: Mapping[str, str] | None = None,
) -> None:
    """Register *log*'s console routes on *app*.

    Auth and *env* capture work as in ``configure_security``.
    """

    def available() -> Response:
        return jsonify({"available": _existing_log(log, env) is not None})

    def stream() -> Response | tuple[Response, int]:
        path = _existing_log(log, env)
        if path is None:
            return jsonify({
                "error": f"{log.name} log unavailable",
                "code": CODE_NOT_FOUND,
                "help": log.help,
            }), HTTPStatus.NOT_FOUND
        offset = initial_offset(request.headers.get("Last-Event-ID", ""))
        return event_stream_response(log.tail(path, offset))

    if log.availability_route:
        app.add_url_rule(
            f"/api/{log.name}/logs/available", endpoint=f"{log.name}_logs_available",
            view_func=available, methods=["GET"],
        )
    app.add_url_rule(
        f"/api/{log.name}/logs/stream", endpoint=f"stream_{log.name}_logs",
        view_func=stream, methods=["GET"],
    )
