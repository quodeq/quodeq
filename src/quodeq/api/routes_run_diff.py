"""GET /api/projects/<project>/runs/<run_id>/diff: one run classified against another."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, request

from quodeq.api._http_cache import conditional_json
from quodeq.api.helpers import json_error, validate_segment
from quodeq.api.routes_common import reports_dir
from quodeq.services.run_diff import diff_runs

_logger = logging.getLogger(__name__)
_QUERY_AGAINST = "against"
_ROUTE = "/api/projects/<project>/runs/<run_id>/diff"


def run_diff(project: str, run_id: str) -> Response | tuple[Response, int]:
    """Diff *run_id* against ``?against=`` or, by default, the previous terminal run."""
    against = request.args.get(_QUERY_AGAINST) or None
    for segment in (project, run_id, *([against] if against else [])):
        err = validate_segment(segment)
        if err is not None:
            return err
    try:
        payload = diff_runs(Path(reports_dir()), project, run_id, against)
    except FileNotFoundError:
        return json_error("Run not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
    except (OSError, ValueError):
        # A report that cannot be read, or a status.json state the parser rejects.
        _logger.exception("Failed to diff run %s for %s", run_id, project)
        return json_error("Failed to diff runs", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
    return conditional_json(payload, max_age=0)


def register_run_diff_routes(app: Flask) -> None:
    """Bind the run-diff route."""
    app.get(_ROUTE)(run_diff)
