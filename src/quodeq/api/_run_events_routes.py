"""SSE route for /api/evaluations/<jobId>/events.

Mirrors the shape of _log_stream_routes.py: resolve job_id to a run dir,
parse Last-Event-ID, return a text/event-stream Response wrapping the
run_events_generator.
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

from quodeq.api._run_event_stream import run_events_generator


def _resolve_run_dir(job_id: str) -> tuple[Path | None, int]:
    """Return (run_dir, status_hint). status_hint is 0 on success, HTTP code on error."""
    provider = current_app.config.get("_provider")
    if provider is None or not hasattr(provider, "get_log_run_dir"):
        return None, HTTPStatus.NOT_FOUND
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None, HTTPStatus.GONE
    return run_dir, 0


def register_run_events_routes(app: Flask) -> None:
    """Register the SSE run-events route on *app*.

    Auth: inherits the global before_request hook from quodeq.api.security.
    """

    @app.get("/api/evaluations/<job_id>/events")
    def stream_run_events(job_id: str) -> Response | tuple[Response, int]:
        run_dir, err = _resolve_run_dir(job_id)
        if run_dir is None:
            return jsonify({"error": "run unavailable", "code": "NOT_FOUND"}), err

        last_event_id_raw = request.headers.get("Last-Event-ID", "")
        try:
            last_event_id = int(last_event_id_raw) if last_event_id_raw else 0
        except ValueError:
            last_event_id = 0

        resp = Response(
            run_events_generator(run_dir, last_event_id=last_event_id),
            mimetype="text/event-stream",
        )
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        return resp
