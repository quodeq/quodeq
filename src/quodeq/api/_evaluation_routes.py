"""Evaluation listing, creation, status, and cancellation route registrations."""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from quodeq.api._evaluation_helpers import (
    _build_evaluation_options,
    _check_eval_rate_limit,
    _sanitize_url,
    _validate_ai_cmd,
)
from quodeq.api.helpers import error_response, validate_evaluation_payload
from quodeq.core.types import to_camel_dict
from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.api.routes import _reports_dir
from quodeq.services.base import ActionProvider
from quodeq.services.evaluation_mixin import _score_completed_evidence
from quodeq.services.scan_progress import build_scan_progress, progress_to_dict
from quodeq.shared.dimensions_state import read_dimensions

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Atomic, bounded "already-scored" registry
# ---------------------------------------------------------------------------
# Keeps track of job_ids whose background scoring has already been claimed so
# that repeated GETs for the same job never spawn more than one scoring thread.
#
# Uses an OrderedDict as a bounded LRU so the registry cannot grow without
# limit on a long-running server.  Access is serialised by a Lock so the
# check-then-add is atomic (closing the TOCTOU race that a plain ``set``
# would have).
_scored_jobs: "OrderedDict[str, None]" = OrderedDict()
_scored_jobs_lock = threading.Lock()
_SCORED_JOBS_MAX = 1000


def _claim_scoring(job_id: str) -> bool:
    """Atomically claim *job_id* for one-time background scoring.

    Returns ``True`` if this caller should start the scoring thread;
    ``False`` if another caller already claimed it.

    The registry is bounded to ``_SCORED_JOBS_MAX`` entries (LRU eviction)
    so memory usage stays constant regardless of server uptime.
    """
    with _scored_jobs_lock:
        if job_id in _scored_jobs:
            return False
        _scored_jobs[job_id] = None
        while len(_scored_jobs) > _SCORED_JOBS_MAX:
            _scored_jobs.popitem(last=False)  # evict oldest entry
        return True


def _read_dim_states(job: Any) -> dict[str, dict[str, Any]]:
    """Read dimensions.json for *job*'s run dir, returning the dimensions map.

    Empty dict on missing/corrupt file (read_dimensions handles that).
    """
    project = getattr(job, "output_project", None)
    run_id = getattr(job, "output_run_id", None)
    if not project or not run_id:
        return {}
    run_dir = Path(_reports_dir()) / project / run_id
    return read_dimensions(run_dir).get("dimensions", {})

# Cap on /api/evaluations ?limit= so a client cannot ask the server to materialize
# an unbounded list. limit=0 still means "no client cap" but we clamp the actual
# value the provider sees. 1000 is well above any realistic dashboard query.
_EVALUATIONS_LIST_HARD_CAP = 1000


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""

    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        raw_limit = request.args.get("limit", 0, type=int)
        if raw_limit <= 0 or raw_limit > _EVALUATIONS_LIST_HARD_CAP:
            limit = _EVALUATIONS_LIST_HARD_CAP
        else:
            limit = raw_limit
        state_arg = request.args.get("state", "").strip()
        states = {s for s in (v.strip() for v in state_arg.split(",")) if s} or None
        items = provider.list_evaluations(limit=limit, reports_dir=_reports_dir(), states=states)
        return jsonify([to_camel_dict(j) for j in items])

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        rate_error = _check_eval_rate_limit(eval_rate_store)
        if rate_error is not None:
            return rate_error
        payload = request.get_json(silent=True) or {}
        validation_error = validate_evaluation_payload(payload)
        if validation_error:
            body, status = error_response(validation_error, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        ai_cmd = payload.get("aiCmd") or None
        ai_cmd_error = _validate_ai_cmd(ai_cmd)
        if ai_cmd_error is not None:
            return ai_cmd_error
        # Require an explicit model for API-type providers (e.g. Ollama)
        if ai_cmd:
            ptype = get_provider_configs().get(ai_cmd, {}).get("type")
            if ptype == "api" and not payload.get("aiModel"):
                body, status = error_response(
                    "No model selected. Go to Settings and select one.",
                    HTTPStatus.BAD_REQUEST, "MODEL_REQUIRED",
                )
                return jsonify(body), status
        repo = payload.get("repo")
        _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
        try:
            options = _build_evaluation_options(payload)
        except ValueError as exc:
            body, status = error_response(str(exc), HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        try:
            job = provider.start_evaluation(repo=repo, reports_dir=_reports_dir(), options=options)
        except (FileNotFoundError, ValueError):
            body, status = error_response(
                "Invalid repository. Provide a local path or a URL like https://github.com/owner/repo.",
                HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
            )
            return jsonify(body), status
        return jsonify(to_camel_dict(job)), HTTPStatus.ACCEPTED


def register_evaluation_item_routes(app: Flask, provider: ActionProvider) -> None:
    """Register single-evaluation status and cancel routes."""

    def reset_scored_jobs() -> None:
        """Clear the scored-jobs registry. Useful for test isolation."""
        with _scored_jobs_lock:
            _scored_jobs.clear()

    app.extensions["reset_scored_jobs"] = reset_scored_jobs

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        job = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if not job:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        # Score any completed dimensions from failed/cancelled jobs (once).
        # Offloaded to a background thread so the GET returns immediately;
        # scoring may involve heavy I/O (reading evidence, writing score files).
        # _claim_scoring() is atomic: exactly one concurrent GET wins the claim.
        job_status = getattr(job, "status", None)
        if job_status in ("failed", "cancelled") and _claim_scoring(job_id):
            _reports = _reports_dir()
            _score_args = {
                "outputProject": job.output_project,
                "outputRunId": job.output_run_id,
            }

            def _score_in_bg(reports_dir: str, score_args: dict) -> None:
                try:
                    _score_completed_evidence(reports_dir, score_args)
                except Exception as exc:
                    _logger.debug(
                        "Could not score cancelled dimension for %s: %s",
                        score_args.get("outputRunId"), exc,
                    )

            threading.Thread(
                target=_score_in_bg,
                args=(_reports, _score_args),
                daemon=True,
            ).start()
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
        # Time limit for the running dim's bar — only available for jobs the
        # JobManager started; external runs surface no budget metadata.
        time_limit_s: int | None = None
        snapshot = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if snapshot is not None:
            options = getattr(snapshot, "options", None) or {}
            # Read new key first; fall back to legacy `poolBudget` for back-compat.
            raw = (
                options.get("timeLimit", options.get("poolBudget"))
                if isinstance(options, dict) else None
            )
            if isinstance(raw, int) and raw > 0:
                time_limit_s = raw
        progress = build_scan_progress(job_id, run_dir, time_limit_s=time_limit_s)
        if progress is None:
            body, status = error_response("Run not ready", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(progress_to_dict(progress)))

    @app.delete("/api/evaluations/<job_id>")
    def cancel_or_delete_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """DELETE on a running job cancels it. DELETE on a finished job removes it from history.

        Query: ``?discard=true`` on a running job also wipes the in-flight
        dim queue + fingerprint snapshots so the next run treats the work
        as never-happened (forces a full rescan for any dim that didn't
        finish scoring on its own).
        """
        snapshot = provider.get_evaluation_status(job_id, reports_dir=_reports_dir())
        if snapshot is None:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        if snapshot.status == "running":
            discard = request.args.get("discard", "").lower() == "true"
            _logger.info(
                "cancel_evaluation: job_id=%s, discard=%s, remote_addr=%s",
                job_id, discard, request.remote_addr,
            )
            ok = provider.cancel_evaluation(
                job_id, reports_dir=_reports_dir(), discard_partial=discard,
            )
            if not ok:
                body, status = error_response("Could not cancel job", HTTPStatus.CONFLICT, "CONFLICT")
                return jsonify(body), status
            return jsonify({"ok": True, "action": "cancelled", "discarded": discard})
        _logger.info("delete_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.delete_evaluation(job_id, reports_dir=_reports_dir())
        if not ok:
            body, status = error_response("Job could not be deleted", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True, "action": "deleted"})
