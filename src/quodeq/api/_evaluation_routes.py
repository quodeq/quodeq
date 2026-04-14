"""Evaluation listing, creation, status, and cancellation route registrations."""
from __future__ import annotations

import logging
from http import HTTPStatus

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

_logger = logging.getLogger(__name__)


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""

    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        limit = request.args.get("limit", 0, type=int)
        items = provider.list_evaluations(limit=limit)
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

    _scored_jobs: set[str] = set()

    def reset_scored_jobs() -> None:
        """Clear the scored-jobs set. Useful for test isolation."""
        _scored_jobs.clear()

    app.extensions["reset_scored_jobs"] = reset_scored_jobs

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        # Score any completed dimensions from failed/cancelled jobs (once)
        job_status = getattr(job, "status", None)
        if job_status in ("failed", "cancelled") and job_id not in _scored_jobs:
            _scored_jobs.add(job_id)
            try:
                _score_completed_evidence(_reports_dir(), {
                    "outputProject": job.output_project,
                    "outputRunId": job.output_run_id,
                })
            except Exception as exc:
                _logger.debug("Could not score cancelled dimension for %s: %s", job_id, exc)
        return jsonify(to_camel_dict(job))

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str) -> Response | tuple[Response, int]:
        _logger.info("cancel_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.cancel_evaluation(job_id, reports_dir=_reports_dir())
        if not ok:
            body, status = error_response("Job not found or not running", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})
