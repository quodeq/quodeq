"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

import os
import time
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request


def _resolve_run_log(job_id: str) -> tuple[Path | None, int]:
    """Return (log_path, status_hint). status_hint is 0 on success, HTTP code on error."""
    provider = current_app.config.get("_provider")
    if provider is None or not hasattr(provider, "get_log_run_dir"):
        return None, HTTPStatus.NOT_FOUND
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None, HTTPStatus.GONE
    log_path = run_dir / "run.log"
    if not log_path.exists():
        return None, HTTPStatus.NOT_FOUND
    return log_path, 0


def _read_tail(log_path: Path, since: int) -> tuple[list[str], int]:
    """Read lines starting at byte offset *since*. Returns (lines, next_offset).

    Drops any trailing partial line (without newline); caller polls again.
    """
    with open(log_path, "rb") as fh:
        fh.seek(since)
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], since  # no complete line yet
        text = text[: last_nl + 1]
    consumed = len(text.encode("utf-8"))
    lines = text.splitlines()
    return lines, since + consumed


_POLL_MS = int(os.environ.get("QUODEQ_LOG_STREAM_POLL_MS", "100"))
_MAX_WAIT_S = int(os.environ.get("QUODEQ_LOG_STREAM_MAX_WAIT_S", "10"))


def _sse_line(data: str, event: str | None = None, event_id: int | None = None) -> str:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}\n")
    if event is not None:
        parts.append(f"event: {event}\n")
    # Escape CR so one log line is one SSE frame.
    parts.append(f"data: {data}\n\n")
    return "".join(parts)


def _sse_generator(log_path: Path, initial_offset: int, is_done):
    """Yield SSE frames by tailing *log_path* starting at *initial_offset*."""
    offset = initial_offset
    waited_ms = 0
    yield ":keepalive\n\n"  # Flask test-client needs at least one byte
    while True:
        if not log_path.exists():
            if waited_ms >= _MAX_WAIT_S * 1000:
                yield _sse_line("log file unavailable", event="error")
                return
            time.sleep(_POLL_MS / 1000)
            waited_ms += _POLL_MS
            continue
        with open(log_path, "rb") as fh:
            fh.seek(offset)
            raw = fh.read()
        text = raw.decode("utf-8", errors="replace")
        if text:
            complete = text if text.endswith("\n") else text[: text.rfind("\n") + 1]
            if complete:
                for line in complete.splitlines():
                    offset += len(line.encode("utf-8")) + 1  # +1 for '\n'
                    yield _sse_line(line, event_id=offset)
        if is_done():
            # Emit done frame without a data field so parsers don't see an empty data entry.
            done_parts = []
            if offset:
                done_parts.append(f"id: {offset}\n")
            done_parts.append("event: done\n\n")
            yield "".join(done_parts)
            return
        time.sleep(_POLL_MS / 1000)


def register_log_stream_routes(app: Flask) -> None:
    """Register plain + SSE log-stream routes on *app*.

    Auth: endpoints inherit protection from the global before_request hook
    in quodeq.api.security._check_auth.
    """

    @app.get("/api/jobs/<job_id>/logs")
    def plain_logs(job_id: str) -> Response | tuple[Response, int]:
        log_path, err = _resolve_run_log(job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        since = max(0, request.args.get("since", 0, type=int))
        lines, next_offset = _read_tail(log_path, since)
        provider = current_app.config.get("_provider")
        done = bool(
            provider and getattr(provider, "is_job_complete", lambda _: False)(job_id)
        )
        return jsonify({"lines": lines, "nextOffset": next_offset, "done": done})

    @app.get("/api/jobs/<job_id>/logs/stream")
    def stream_logs(job_id: str) -> Response | tuple[Response, int]:
        log_path, err = _resolve_run_log(job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        last_event_id = request.headers.get("Last-Event-ID", "")
        try:
            initial_offset = int(last_event_id) if last_event_id else 0
        except ValueError:
            initial_offset = 0
        provider = current_app.config.get("_provider")
        is_done = (
            lambda: bool(
                provider
                and getattr(provider, "is_job_complete", lambda _: False)(job_id)
            )
        )

        resp = Response(
            _sse_generator(log_path, initial_offset, is_done),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
