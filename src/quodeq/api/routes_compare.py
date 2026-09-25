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

from quodeq.api._constants import CODE_NOT_FOUND
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.services.compare import build_compare_summary

_logger = logging.getLogger(__name__)


def register_compare_routes(app: Flask) -> None:
    """Register the Compare summary endpoint."""

    @app.get("/api/projects/<project>/compare-summary")
    def project_compare_summary(project: str) -> Response | tuple[Response, int]:
        err = validate_segment(project)
        if err is not None:
            return err
        try:
            result = build_compare_summary(Path(reports_dir()), project)
        except Exception:
            _logger.exception("Unexpected error building compare summary for project %s", project)
            return json_error("Failed to load compare summary", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
        if result is None:
            return json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return jsonify(result)
