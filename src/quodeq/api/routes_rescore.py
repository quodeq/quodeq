"""API route for live rescoring after dismissals."""
from __future__ import annotations

from pathlib import Path
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import json_error
from quodeq.services.rescore_run import rescore_project_run
from quodeq.shared.utils import get_evaluations_dir


def _eval_dir_from_app(app: Flask) -> str:
    return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()


# Use-case outcome -> (message, HTTP status, code). The route owns only this
# mapping plus query parsing; the rules live in services.rescore_run.
_OUTCOME_ERRORS = {
    "invalid_param": ("Invalid project or run parameter", HTTPStatus.BAD_REQUEST, "INVALID_PARAM"),
    "project_not_found": ("No runs found for project", HTTPStatus.NOT_FOUND, "NOT_FOUND"),
    "run_not_found": ("Run data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND"),
}


def register_rescore_routes(app: Flask) -> None:
    """Register the GET /api/rescore route on *app*.

    Example:
        GET /api/rescore?project=my-project
        GET /api/rescore?project=my-project&run=run-42
    """

    @app.get("/api/rescore")
    def rescore() -> Response | tuple[Response, int]:
        project = request.args.get("project", "")
        if not project:
            return json_error(
                "project query parameter is required; add ?project=<name> to the query string",
                HTTPStatus.BAD_REQUEST, "MISSING_PARAM",
            )
        run_id = request.args.get("run", "")
        eval_dir = _eval_dir_from_app(app)

        outcome = rescore_project_run(Path(eval_dir), project, run_id)
        if outcome.status != "ok":
            message, http_status, code = _OUTCOME_ERRORS[outcome.status]
            return json_error(message, http_status, code)
        return jsonify(outcome.result)
