"""Single-evaluation status, progress, cancel, and delete routes."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from quodeq.api._scored_jobs_registry import _claim_scoring, _release_scoring, reset_scored_jobs
from quodeq.api.helpers import error_response
from quodeq.shared.serialization import to_camel_dict
from quodeq.api.routes import _reports_dir
from quodeq.services.background import BackgroundRunner, ThreadBackgroundRunner
from quodeq.services.base import ActionProvider
from quodeq.services.scan_progress import build_scan_progress
from quodeq.services.run_events import read_run_dim_states

_logger = logging.getLogger(__name__)


def _background(app: Flask) -> BackgroundRunner:
    """The app's background-task runner. ``create_app`` instantiates it;
    setdefault keeps bare test apps (register_evaluation_item_routes on a
    plain Flask) working."""
    return app.extensions.setdefault("background", ThreadBackgroundRunner())


def _read_dim_states(job: Any) -> dict[str, dict[str, Any]]:
    """Read dimensions.json for *job*'s run dir, returning the dimensions map.

    Empty dict on missing/corrupt file (read_dimensions handles that).
    """
    project = getattr(job, "output_project", None)
    run_id = getattr(job, "output_run_id", None)
    if not project or not run_id:
        return {}
    return read_run_dim_states(_reports_dir(), project, run_id)


def _score_completed_dims_in_bg(app: Flask, job: Any) -> None:
    """Score completed dimensions of a failed/cancelled *job*, once.

    Offloaded to a background thread so the GET returns immediately;
    scoring may involve heavy I/O (reading evidence, writing score files).
    _claim_scoring() is atomic: exactly one concurrent GET wins the claim.
    """
    job_status = getattr(job, "status", None)
    if job_status not in ("failed", "cancelled"):
        return
    job_id = job.job_id
    if not _claim_scoring(job_id):
        return
    _reports = _reports_dir()
    _score_args = {
        "outputProject": job.output_project,
        "outputRunId": job.output_run_id,
    }

    def _score_in_bg() -> None:
        # Deferred so a patch on quodeq.api._evaluation_routes.score_completed_evidence
        # (the public patch target) is honored regardless of this module.
        from quodeq.api import _evaluation_routes as _facade
        try:
            _facade.score_completed_evidence(_reports, _score_args)
        except Exception as exc:
            _logger.debug(
                "Could not score cancelled dimension for %s: %s",
                _score_args.get("outputRunId"), exc,
            )

    _background(app).submit(_score_in_bg, name=f"score-{job_id}")


def _resolve_cancel_intent(snapshot: Any, intent: str | None) -> tuple[dict, int] | None:
    """Validate a declared ``?intent=`` against the job's current status.

    Returns an ``(body, status)`` error pair if the intent conflicts with
    the status, else ``None`` to let the caller proceed.
    """
    if intent == "cancel" and snapshot.status != "running":
        return error_response(
            "Evaluation already finished. Nothing was cancelled.",
            HTTPStatus.CONFLICT, "ALREADY_FINISHED",
        )
    if intent == "delete" and snapshot.status == "running":
        return error_response(
            "Evaluation is still running. Cancel it before deleting.",
            HTTPStatus.CONFLICT, "STILL_RUNNING",
        )
    return None


def register_evaluation_item_routes(app: Flask, provider: ActionProvider) -> None:
    """Register single-evaluation status and cancel routes."""

    app.extensions["reset_scored_jobs"] = reset_scored_jobs

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        job = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if not job:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        _score_completed_dims_in_bg(app, job)
        payload = to_camel_dict(job)
        payload["dimStates"] = _read_dim_states(job)
        return jsonify(payload)

    @app.get("/api/evaluations/<job_id>/progress")
    def get_evaluation_progress(job_id: str) -> Response | tuple[Response, int]:
        """Return live progress for a scan (works for internal and external runs)."""
        run_dir = provider.get_log_run_dir(job_id) if hasattr(provider, "get_log_run_dir") else None
        if run_dir is None:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        # Total time limit for the whole run. The snapshot carries the
        # budget for both internal jobs (JobManager) and index-served runs
        # (read from status.json). 0 = unlimited -> no budget shown.
        time_limit_s: int | None = None
        snapshot = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if snapshot is not None:
            raw = getattr(snapshot, "time_limit_s", None)
            if isinstance(raw, int) and raw > 0:
                time_limit_s = raw
        progress = build_scan_progress(
            job_id, run_dir, time_limit_s=time_limit_s,
            compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
        )
        if progress is None:
            body, status = error_response("Run not ready", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(progress))

    @app.delete("/api/evaluations/<job_id>")
    def cancel_or_delete_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """DELETE on a running job cancels it. DELETE on a finished job removes it from history.

        Query: ``?intent=cancel|delete`` declares what the client is asking
        for. Without it, the action is inferred from the momentary status
        (legacy behavior), which is race-prone: a run finishing while the
        cancel dialog is open, or a double-clicked cancel, used to fall
        through to the permanent-purge branch and erase a run the user
        chose to keep. With intent=cancel this endpoint can never purge;
        with intent=delete it never silently cancels.

        ``?discard=true`` on a cancel also wipes the run entirely so the
        next run treats the work as never-happened.
        """
        snapshot = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if snapshot is None:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        intent = request.args.get("intent", "").lower() or None
        conflict = _resolve_cancel_intent(snapshot, intent)
        if conflict is not None:
            body, status = conflict
            return jsonify(body), status
        if snapshot.status == "running":
            discard = request.args.get("discard", "").lower() == "true"
            _logger.info(
                "cancel_evaluation: job_id=%s, discard=%s, remote_addr=%s",
                job_id, discard, request.remote_addr,
            )
            if discard:
                # Claim the one-time scoring slot BEFORE the job flips to
                # cancelled: otherwise the UI's next status poll sees the
                # cancelled state and spawns _score_completed_evidence,
                # resurrecting a run the user just discarded.
                _claim_scoring(job_id)
            ok = provider.cancel_evaluation(
                job_id, reports_dir=_reports_dir(), discard_partial=discard,
            )
            if not ok:
                if discard:
                    _release_scoring(job_id)
                body, status = error_response("Could not cancel job", HTTPStatus.CONFLICT, "CONFLICT")
                return jsonify(body), status
            return jsonify({"ok": True, "action": "cancelled", "discarded": discard})
        _logger.info("delete_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.delete_evaluation(job_id, reports_dir=_reports_dir())
        if not ok:
            body, status = error_response("Job could not be deleted", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True, "action": "deleted"})
