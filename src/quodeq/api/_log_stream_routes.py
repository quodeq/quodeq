"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

import functools
from http import HTTPStatus

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api._log_tail_helpers import (
    _is_visible_log_line,
    _read_tail,
    _resolve_run_log,
    _resolve_stream_log_path,
    _stream_terminal_state,
)
from quodeq.api._sse_log_helpers import sse_tail_generator as _sse_tail_generator
from quodeq.shared.validation import validate_path_segment


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
    if jobs is not None:
        job = jobs.get_job(job_id)
        if job is not None and job.status not in {"done", "failed", "cancelled"}:
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


def register_log_stream_routes(app: Flask) -> None:
    """Register plain + SSE log-stream routes on *app*.

    Auth: endpoints inherit protection from the global before_request hook
    in quodeq.api.security._check_auth.
    """

    @app.get("/api/jobs/<job_id>/logs")
    def plain_logs(job_id: str) -> Response | tuple[Response, int]:
        try:
            validate_path_segment(job_id)
        except ValueError:
            return jsonify({"error": "invalid job id", "code": "INVALID_INPUT"}), HTTPStatus.BAD_REQUEST
        provider = current_app.config.get("_provider")
        log_path, err = _resolve_run_log(provider, job_id)
        if log_path is None:
            return jsonify({"error": "log unavailable", "code": "NOT_FOUND"}), err
        since = max(0, request.args.get("since", 0, type=int))
        lines, next_offset = _read_tail(log_path, since)
        done = bool(
            provider and getattr(provider, "is_job_complete", lambda _: False)(job_id)
        )
        return jsonify({"lines": lines, "nextOffset": next_offset, "done": done})

    @app.get("/api/jobs/<job_id>/logs/stream")
    def stream_logs(job_id: str) -> Response | tuple[Response, int]:
        try:
            validate_path_segment(job_id)
        except ValueError:
            return jsonify({"error": "invalid job id", "code": "INVALID_INPUT"}), HTTPStatus.BAD_REQUEST
        provider = current_app.config.get("_provider")
        log_path, err = _resolve_run_log(provider, job_id)
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

        resp = Response(
            _sse_tail_generator(
                functools.partial(_resolve_stream_log_path, provider, job_id),
                initial_offset,
                is_done=is_done,
                line_filter=_is_visible_log_line,
                terminal_state=functools.partial(_stream_terminal_state, provider, job_id),
            ),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
