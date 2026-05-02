"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api._sse_log_helpers import sse_tail_generator as _sse_tail_generator

# Lines containing this marker are kept in run.log for forensics but suppressed
# from the dashboard's live console — they're per-minute resource snapshots
# (rss / fds / threads / ollama RSS) and clutter the operator-facing view.
_CONSOLE_HIDDEN_MARKERS: tuple[str, ...] = ("[resources]",)

# Per-poll byte cap: a single tail read will not pull more than this many bytes
# into memory in one shot. The remaining bytes will be served on the next poll.
# Caps a runaway log file from blowing out RAM on read.
_DEFAULT_TAIL_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


def _tail_max_bytes() -> int:
    raw = os.environ.get("QUODEQ_LOG_TAIL_MAX_BYTES")
    if not raw:
        return _DEFAULT_TAIL_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TAIL_MAX_BYTES
    return value if value > 0 else _DEFAULT_TAIL_MAX_BYTES


def _is_visible_log_line(line: str) -> bool:
    return not any(marker in line for marker in _CONSOLE_HIDDEN_MARKERS)


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


def _is_preparing_job(provider, job_id: str) -> bool:
    """Return True if *job_id* refers to a job that may still produce output.

    Used by the SSE log-stream route to keep the EventSource alive while a
    runner is in the "preparing" phase — resolving inputs, cloning a remote
    repo, creating the run directory — but hasn't yet emitted the
    ``report_path`` marker that lets the dashboard locate ``run.log``.

    Returns False for unknown ids so a typo or a stale jobId from the
    client doesn't keep a connection (and a polling Python thread) open
    forever.
    """
    if provider is None:
        return False
    # Internal job: must be in the in-memory store with a non-terminal
    # status. Pre-marker, ``output_project`` is None so ``get_log_run_dir``
    # returns None — without this check the route would 404 the moment the
    # frontend opens the stream after Start.
    jobs = getattr(provider, "_jobs", None)
    store = getattr(jobs, "_store", None) if jobs is not None else None
    if store is not None:
        job = store.get(job_id)
        if job is not None and getattr(job, "status", None) not in {
            "done", "failed", "cancelled",
        }:
            return True
    # External job: the CLI creates the run directory before opening the
    # ``run.log`` writer, so there is a brief window where the directory
    # exists but the file does not. If the provider can resolve a real
    # run_dir, treat the run as live.
    if hasattr(provider, "get_log_run_dir"):
        run_dir = provider.get_log_run_dir(job_id)
        if run_dir is not None and run_dir.is_dir():
            return True
    return False


def _read_tail(log_path: Path, since: int) -> tuple[list[str], int]:
    """Read lines starting at byte offset *since*. Returns (lines, next_offset).

    Drops any trailing partial line (without newline); caller polls again.
    """
    with open(log_path, "rb") as fh:
        fh.seek(since)
        raw = fh.read(_tail_max_bytes())
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], since  # no complete line yet
        text = text[: last_nl + 1]
    consumed = len(text.encode("utf-8"))
    lines = [ln for ln in text.splitlines() if _is_visible_log_line(ln)]
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

    @app.get("/api/jobs/<job_id>/logs/stream")
    def stream_logs(job_id: str) -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        log_path, err = _resolve_run_log(job_id)
        # If run.log isn't on disk yet but the job is still preparing
        # (no report_path marker yet, or the runner just hasn't created
        # the file), keep the SSE response open and let the generator
        # wait for the file to appear. Only refuse for jobs we cannot
        # recognise as live — otherwise the dashboard pane would show
        # "stream disconnected" until the user reopens the console.
        if log_path is None and not _is_preparing_job(provider, job_id):
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        last_event_id = request.headers.get("Last-Event-ID", "")
        try:
            initial_offset = int(last_event_id) if last_event_id else 0
        except ValueError:
            initial_offset = 0
        is_done = (
            lambda: bool(
                provider
                and getattr(provider, "is_job_complete", lambda _: False)(job_id)
            )
        )

        def resolve_log_path() -> Path | None:
            # Re-resolved each tick. A job that started in the
            # "preparing" state (no output_project yet) eventually emits
            # the report_path marker; from then on get_log_run_dir
            # returns the real run dir and run.log appears.
            if not hasattr(provider, "get_log_run_dir"):
                return None
            run_dir = provider.get_log_run_dir(job_id)
            if run_dir is None or not run_dir.is_dir():
                return None
            return run_dir / "run.log"

        def terminal_state() -> str:
            # In-memory job (internal runs) carries the most up-to-date status
            # before the runner has flushed status.json — prefer it.
            if provider is not None and hasattr(provider, "_jobs"):
                store = getattr(provider._jobs, "_store", None)
                if store is not None:
                    job = store.get(job_id)
                    if job is not None and job.status in {"done", "failed", "cancelled"}:
                        return job.status
            # Fall back to the on-disk status.json the runner writes on exit.
            path = resolve_log_path()
            if path is None:
                return "completed"
            status_path = path.parent / "status.json"
            if status_path.exists():
                try:
                    import json
                    data = json.loads(status_path.read_text())
                    state = data.get("state")
                    if isinstance(state, str):
                        return state
                except (OSError, ValueError):
                    pass
            return "completed"

        resp = Response(
            _sse_tail_generator(
                resolve_log_path,
                initial_offset,
                is_done=is_done,
                line_filter=_is_visible_log_line,
                terminal_state=terminal_state,
            ),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
