"""SSE route for /api/evaluations/<jobId>/events.

Mirrors the shape of _log_stream_routes.py: resolve job_id to a run dir,
parse Last-Event-ID, return a text/event-stream Response wrapping the
run_events_generator.

A job that is still preparing (no report_path marker yet, so no run dir)
gets a stream that waits for the dir instead of a 410. The browser's
EventSource never retries after a non-200, so answering 410 in that window
left the Evaluate screen without live findings for the whole run.
"""
from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, request

from quodeq.api._constants import CODE_GONE, CODE_NOT_FOUND
from quodeq.api._log_tail_helpers import is_preparing_job, resolve_run_dir
from quodeq.api._run_event_stream import run_events_generator, run_events_generator_awaiting_dir
from quodeq.api._sse_log_helpers import event_stream_response
from quodeq.api.helpers import json_error
from quodeq.core.run.job_status import JobStatus


def _parse_last_event_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _job_is_complete(provider, job_id: str) -> bool:
    is_complete = getattr(provider, "is_job_complete", None)
    return bool(is_complete(job_id)) if callable(is_complete) else False


def _terminal_state(provider, job_id: str) -> str:
    in_memory_job = getattr(provider, "in_memory_job", None)
    job = in_memory_job(job_id) if callable(in_memory_job) else None
    return str(getattr(job, "status", None) or JobStatus.FAILED)


def _awaiting_run_dir_stream(provider, job_id: str, last_event_ts: datetime | None):
    def resolve() -> Path | None:
        run_dir, _err = resolve_run_dir(provider, job_id)
        return run_dir

    return run_events_generator_awaiting_dir(
        resolve,
        lambda: _job_is_complete(provider, job_id),
        lambda: _terminal_state(provider, job_id),
        last_event_ts=last_event_ts,
    )


def register_run_events_routes(app: Flask) -> None:
    """Register the SSE run-events route on *app*.

    Auth: inherits the global before_request hook from quodeq.api.security.
    """

    @app.get("/api/evaluations/<job_id>/events")
    def stream_run_events(job_id: str) -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        last_event_ts = _parse_last_event_ts(request.headers.get("Last-Event-ID", ""))
        run_dir, err = resolve_run_dir(provider, job_id)
        if run_dir is not None:
            return event_stream_response(run_events_generator(run_dir, last_event_ts=last_event_ts))
        if is_preparing_job(provider, job_id):
            return event_stream_response(_awaiting_run_dir_stream(provider, job_id, last_event_ts))
        code = CODE_GONE if err == HTTPStatus.GONE else CODE_NOT_FOUND
        return json_error("run unavailable", err, code)
