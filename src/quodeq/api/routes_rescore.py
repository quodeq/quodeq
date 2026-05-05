"""API route for live rescoring after dismissals."""
from __future__ import annotations

from pathlib import Path
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.services.ports import list_runs, read_run_data
from quodeq.services.deleted import deleted_keys as load_deleted_keys
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys
from quodeq.services.rescore import rescore_dimensions
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import validate_path_segment


def _eval_dir_from_app(app: Flask) -> str:
    return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()


def register_rescore_routes(app: Flask) -> None:
    """Register /api/rescore route."""

    @app.get("/api/rescore")
    def rescore() -> Response | tuple[Response, int]:
        project = request.args.get("project", "")
        if not project:
            body, status = error_response("project query parameter is required", HTTPStatus.BAD_REQUEST, "MISSING_PARAM")
            return jsonify(body), status
        run_id = request.args.get("run", "")
        try:
            validate_path_segment(project)
            if run_id and run_id != "latest":
                validate_path_segment(run_id)
        except ValueError:
            body, status = error_response("Invalid project or run parameter", HTTPStatus.BAD_REQUEST, "INVALID_PARAM")
            return jsonify(body), status
        eval_dir = _eval_dir_from_app(app)

        # Resolve run ID
        if not run_id or run_id == "latest":
            runs = list_runs(Path(eval_dir), project, limit=1)
            if not runs:
                body, status = error_response("No runs found for project", HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return jsonify(body), status
            run_id = runs[0].run_id

        try:
            dimensions = read_run_data(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Run data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        project_dir = Path(eval_dir) / project
        dismissed = load_dismissed_keys(project_dir)
        deleted = load_deleted_keys(project_dir)

        result = rescore_dimensions(dimensions, dismissed, deleted)
        return jsonify(result)
