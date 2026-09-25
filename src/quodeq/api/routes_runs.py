"""GET /api/projects/<project>/runs — the `runs` UI data unit."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response

from quodeq.api._http_cache import conditional_json
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.services.runs_unit import build_runs_unit
from quodeq.shared.env import get_index_db_path

_logger = logging.getLogger(__name__)


def register_runs_routes(app: Flask) -> None:
    """Bind GET /api/projects/<project>/runs."""
    @app.get("/api/projects/<project>/runs")
    def project_runs(project: str) -> Response | tuple[Response, int]:
        err = validate_segment(project)
        if err is not None:
            return err
        try:
            runs = build_runs_unit(Path(reports_dir()), Path(get_index_db_path()), project)
        except Exception:
            _logger.exception("Failed to build runs unit for %s", project)
            return json_error("Failed to load runs", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
        return conditional_json({"runs": runs}, max_age=0)
