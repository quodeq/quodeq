"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

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
