"""Compare-screen endpoints.

/api/fleet/compare?projects=a,b,c -- the slim accumulated scores + trend of
every listed project in one response, findings stripped, over one
score-cache connection. A project that is unknown or fails to build is
reported in ``errors`` by name and does not block the others.

/api/projects/{project}/compare-summary -- the same summary for one project.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_INTERNAL_ERROR, CODE_NOT_FOUND
from quodeq.api.fleet_request import FLEET_LOG, fleet_projects_or_error
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.services.compare import COMPARE_ERRORS, build_compare_summary, build_fleet_compare

_logger = logging.getLogger(__name__)


def register_compare_routes(app: Flask) -> None:
    """Register the Compare endpoints."""

    @app.get("/api/fleet/compare")
    def fleet_compare() -> Response | tuple[Response, int]:
        names = fleet_projects_or_error()
        if not isinstance(names, list):
            return names
        return jsonify(build_fleet_compare(Path(reports_dir()), names, log=FLEET_LOG))

    @app.get("/api/projects/<project>/compare-summary")
    def project_compare_summary(project: str) -> Response | tuple[Response, int]:
        err = validate_segment(project)
        if err is not None:
            return err
        try:
            result = build_compare_summary(Path(reports_dir()), project)
        except COMPARE_ERRORS:
            _logger.exception("Unexpected error building compare summary for project %s", project)
            return json_error("Failed to load compare summary", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR)
        if result is None:
            return json_error("Project not found", HTTPStatus.NOT_FOUND, CODE_NOT_FOUND)
        return jsonify(result)
