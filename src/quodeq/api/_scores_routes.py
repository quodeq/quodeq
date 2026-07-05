"""Unified scoring API endpoints.

/api/projects/{project}/scores          -- full dashboard payload (accumulated + trend)
/api/projects/{project}/scores/{runId}  -- single run detail (for Explorer)

All rescore logic happens server-side. The frontend never calls /api/rescore
directly when using these endpoints.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def register_scores_routes(app: Flask) -> None:
    """Register unified scoring endpoints."""

    def _validate(*params: str) -> tuple[Response, int] | None:
        try:
            validate_path_segment(*params)
        except ValueError:
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return None

    @app.get("/api/projects/<project>/scores")
    def project_scores(project: str) -> Response | tuple[Response, int]:
        err = _validate(project)
        if err:
            return err
        as_of = request.args.get("asOf")
        eval_dir = reports_dir()
        try:
            result = get_project_scores(Path(eval_dir), project, as_of)
        except Exception:
            _logger.exception("Unexpected error fetching scores for project %s", project)
            body, status = error_response("Failed to load scores", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        if result is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)

    @app.get("/api/projects/<project>/scores/<run_id>")
    def project_run_scores(project: str, run_id: str) -> Response | tuple[Response, int]:
        err = _validate(project, run_id)
        if err:
            return err
        eval_dir = reports_dir()
        try:
            result = get_scores_slim(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Run not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)
