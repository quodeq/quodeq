"""Compare-screen endpoint.

/api/projects/{project}/compare-summary -- slim accumulated scores + trend
for one project, findings stripped. The Compare tab fans out one request per
project so rows render progressively and a single cold project can't block
the whole fleet view.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.services.compare import build_compare_summary
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def register_compare_routes(app: Flask) -> None:
    """Register the Compare summary endpoint."""

    @app.get("/api/projects/<project>/compare-summary")
    def project_compare_summary(project: str) -> Response | tuple[Response, int]:
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        try:
            result = build_compare_summary(Path(reports_dir()), project)
        except Exception:
            _logger.exception("Unexpected error building compare summary for project %s", project)
            body, status = error_response("Failed to load compare summary", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        if result is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(result)
