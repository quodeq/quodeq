"""SSE route for /api/evaluations/<jobId>/events.

Mirrors the shape of _log_stream_routes.py: resolve job_id to a run dir,
parse Last-Event-ID, return a text/event-stream Response wrapping the
run_events_generator.
"""
from __future__ import annotations

from datetime import datetime
from http import HTTPStatus

from flask import Flask, Response, current_app, request

from quodeq.api._constants import CODE_GONE, CODE_NOT_FOUND
from quodeq.api._log_tail_helpers import resolve_run_dir
from quodeq.api._run_event_stream import run_events_generator
from quodeq.api._sse_log_helpers import event_stream_response
from quodeq.api.helpers import json_error


def register_run_events_routes(app: Flask) -> None:
    """Register the SSE run-events route on *app*.

    Auth: inherits the global before_request hook from quodeq.api.security.
    """

    @app.get("/api/evaluations/<job_id>/events")
    def stream_run_events(job_id: str) -> Response | tuple[Response, int]:
        run_dir, err = resolve_run_dir(current_app.config.get("_provider"), job_id)
        if run_dir is None:
            code = CODE_GONE if err == HTTPStatus.GONE else CODE_NOT_FOUND
            return json_error("run unavailable", err, code)

        last_event_id_raw = request.headers.get("Last-Event-ID", "")
        last_event_ts: datetime | None = None
        if last_event_id_raw:
            try:
                last_event_ts = datetime.fromisoformat(last_event_id_raw)
            except ValueError:
                last_event_ts = None

        return event_stream_response(run_events_generator(run_dir, last_event_ts=last_event_ts))
