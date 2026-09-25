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
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.services.scoring import get_project_scores, get_scores_slim
from quodeq.services.scoring.compliance_detail import compliance_detail, defer_compliance_detail

_logger = logging.getLogger(__name__)


def _load_scores(project: str) -> tuple[dict | None, tuple[Response, int] | None]:
    as_of = request.args.get("asOf")
    eval_dir = reports_dir()
    try:
        result = get_project_scores(Path(eval_dir), project, as_of)
    except Exception:
        _logger.exception("Unexpected error fetching scores for project %s", project)
        return None, json_error("Failed to load scores", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
    if result is None:
        return None, json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
    return result, None


def register_scores_routes(app: Flask) -> None:
    """Register unified scoring endpoints."""

    @app.get("/api/projects/<project>/scores")
    def project_scores(project: str) -> Response | tuple[Response, int]:
        err = validate_segment(project)
        if err:
            return err
        result, err = _load_scores(project)
        if err:
            return err
        return jsonify(defer_compliance_detail(result))

    @app.get("/api/projects/<project>/scores/<run_id>")
    def project_run_scores(project: str, run_id: str) -> Response | tuple[Response, int]:
        err = validate_segment(project, run_id)
        if err:
            return err
        eval_dir = reports_dir()
        try:
            result = get_scores_slim(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            return json_error("Run not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        except Exception:
            _logger.exception("Unexpected error fetching run scores for project %s run %s", project, run_id)
            return json_error(
                "could not read run scores", HTTPStatus.INTERNAL_SERVER_ERROR, "SCORES_READ_FAILED"
            )
        return jsonify(result)

    _register_compliance_detail_route(app)


def _register_compliance_detail_route(app: Flask) -> None:
    @app.get("/api/projects/<project>/compliance-detail")
    def project_compliance_detail(project: str) -> Response | tuple[Response, int]:
        dimension = request.args.get("dimension")
        if not dimension:
            return json_error("dimension is required", HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
        err = validate_segment(project, dimension)
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
