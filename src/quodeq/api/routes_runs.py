"""GET /api/projects/<project>/runs — the `runs` UI data unit."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api._http_cache import conditional_json
from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.services._runs_unit import build_runs_unit
from quodeq.shared._env import get_index_db_path
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def register_runs_routes(app: Flask) -> None:
    @app.get("/api/projects/<project>/runs")
    def project_runs(project: str) -> Response | tuple[Response, int]:
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid parameter", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        try:
            runs = build_runs_unit(Path(reports_dir()), Path(get_index_db_path()), project)
        except Exception:
            _logger.exception("Failed to build runs unit for %s", project)
            body, status = error_response("Failed to load runs", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        return conditional_json({"runs": runs}, max_age=0)
