"""Log-stream routes — SSE live stream + plain JSON fallback for /api/jobs/<id>/logs."""
from __future__ import annotations

import functools
from http import HTTPStatus

from flask import Flask, Response, current_app, jsonify, request

from quodeq.core.run.job_status import JOB_FINISHED
from quodeq.api._constants import CODE_INVALID_INPUT, CODE_NOT_FOUND
from quodeq.api._log_tail_helpers import (
    is_visible_log_line,
    read_tail,
    resolve_run_log,
    resolve_stream_log_path,
    stream_terminal_state,
)
from quodeq.api._sse_log_helpers import event_stream_response, initial_offset
from quodeq.api._sse_log_helpers import sse_tail_generator as _sse_tail_generator
from quodeq.api.helpers import json_error
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
    job = provider.in_memory_job(job_id)
    if job is not None and job.status not in JOB_FINISHED:
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


def _job_done_checker(provider, job_id: str):
    """Return a zero-arg callable reporting whether *job_id* has completed."""
    def is_done() -> bool:
        return bool(
            provider and getattr(provider, "is_job_complete", lambda _: False)(job_id)
        )
    return is_done


def _sse_log_response(provider, job_id: str, offset: int) -> Response:
    """Build the ``text/event-stream`` response tailing *job_id*'s run.log."""
    return event_stream_response(_sse_tail_generator(
        functools.partial(resolve_stream_log_path, provider, job_id),
        offset,
        is_done=_job_done_checker(provider, job_id),
        line_filter=is_visible_log_line,
        terminal_state=functools.partial(stream_terminal_state, provider, job_id),
    ))


def _invalid_job_id() -> tuple[Response, int]:
    """The 400 both log routes answer a malformed job id with."""
    return json_error("invalid job id", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)


def _log_unavailable(status: int) -> tuple[Response, int]:
    """The error both log routes answer an absent run.log with, at *status*."""
    return json_error("log unavailable", status, CODE_NOT_FOUND)


def _job_log_inputs(job_id: str):
    """``(provider, log_path, status)`` for *job_id*, or None when the id is malformed.

    *status* is the HTTP status ``resolve_run_log`` chose for an absent log;
    what an absent log means is the route's own call.
    """
    try:
        validate_path_segment(job_id)
    except ValueError:
        return None
    provider = current_app.config.get("_provider")
    log_path, err = resolve_run_log(provider, job_id)
    return provider, log_path, err


def register_log_stream_routes(app: Flask) -> None:
    """Register plain + SSE log-stream routes on *app*.

    Auth: endpoints inherit protection from the global before_request hook
    in quodeq.api.security._check_auth.
    """

    @app.get("/api/jobs/<job_id>/logs")
    def plain_logs(job_id: str) -> Response | tuple[Response, int]:
        resolved = _job_log_inputs(job_id)
        if resolved is None:
            return _invalid_job_id()
        provider, log_path, err = resolved
        if log_path is None:
            return _log_unavailable(err)
        since = max(0, request.args.get("since", 0, type=int))
        lines, next_offset = read_tail(log_path, since)
        done = _job_done_checker(provider, job_id)()
        return jsonify({"lines": lines, "nextOffset": next_offset, "done": done})

    @app.get("/api/jobs/<job_id>/logs/stream")
    def stream_logs(job_id: str) -> Response | tuple[Response, int]:
        resolved = _job_log_inputs(job_id)
        if resolved is None:
            return _invalid_job_id()
        provider, log_path, err = resolved
        # If run.log isn't on disk yet but the job is still preparing
        # (no report_path marker yet, or the runner just hasn't created
        # the file), keep the SSE response open and let the generator
        # wait for the file to appear. Only refuse for jobs we cannot
        # recognise as live — otherwise the dashboard pane would show
        # "stream disconnected" until the user reopens the console.
        if log_path is None and not _is_preparing_job(provider, job_id):
            return _log_unavailable(err)
        offset = initial_offset(request.headers.get("Last-Event-ID", ""))
        return _sse_log_response(provider, job_id, offset)
