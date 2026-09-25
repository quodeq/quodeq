"""Unified scoring API endpoints.

/api/projects/{project}/scores          -- full dashboard payload (accumulated + trend)
/api/projects/{project}/scores/{runId}  -- single run detail (for Explorer)
/api/projects/{project}/compliance-detail -- compliance detail /scores defers

All rescore logic happens server-side. The frontend never calls /api/rescore
directly when using these endpoints.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_INPUT, CODE_NOT_FOUND
from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.scoring.compliance_detail import compliance_detail, defer_compliance_detail
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def _validate(*params: str) -> tuple[Response, int] | None:
    try:
        validate_path_segment(*params)
    except ValueError:
        body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
        return jsonify(body), status
    return None


def _load_scores(project: str) -> tuple[dict | None, tuple[Response, int] | None]:
    as_of = request.args.get("asOf")
    eval_dir = reports_dir()
    try:
        result = get_project_scores(Path(eval_dir), project, as_of)
    except Exception:
        _logger.exception("Unexpected error fetching scores for project %s", project)
        body, status = error_response("Failed to load scores", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
        return None, (jsonify(body), status)
    if result is None:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return None, (jsonify(body), status)
    return result, None


def register_scores_routes(app: Flask) -> None:
    """Register unified scoring endpoints."""

    @app.get("/api/projects/<project>/scores")
    def project_scores(project: str) -> Response | tuple[Response, int]:
        err = _validate(project)
        if err:
            return err
        result, err = _load_scores(project)
        if err:
            return err
        return jsonify(defer_compliance_detail(result))

    @app.get("/api/projects/<project>/scores/<run_id>")
    def project_run_scores(project: str, run_id: str) -> Response | tuple[Response, int]:
        err = _validate(project, run_id)
        if err:
            return err
        eval_dir = reports_dir()
        try:
            result = get_scores_slim(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
            return jsonify(body), status
        except Exception:
            _logger.exception("Unexpected error fetching run scores for project %s run %s", project, run_id)
            body, status = error_response(
                "could not read run scores", HTTPStatus.INTERNAL_SERVER_ERROR, "SCORES_READ_FAILED"
            )
            return jsonify(body), status
        return jsonify(result)

    _register_compliance_detail_route(app)


def _register_compliance_detail_route(app: Flask) -> None:
    @app.get("/api/projects/<project>/compliance-detail")
    def project_compliance_detail(project: str) -> Response | tuple[Response, int]:
        dimension = request.args.get("dimension")
        if not dimension:
            body, status = error_response("dimension is required", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
            return jsonify(body), status
        err = _validate(project, dimension)
        if err:
            return err
        result, err = _load_scores(project)
        if err:
            return err
        items = compliance_detail(
            result, dimension,
            principle=request.args.get("principle"),
            path_prefix=request.args.get("pathPrefix"),
        )
        return jsonify({"items": items})
