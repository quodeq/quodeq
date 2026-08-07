"""API route for live rescoring after dismissals."""
from __future__ import annotations

from pathlib import Path
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.services.run_reports import list_runs, read_run_data
from quodeq.services.deleted import deleted_keys as load_deleted_keys
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys
from quodeq.services.rescore import rescore_dimensions
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import resolve_child_dir, validate_path_segment
from quodeq.services.suppression import load_suppression_rules


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
        eval_dir = _eval_dir_from_app(app)
        try:
            validate_path_segment(project)
            if run_id and run_id != "latest":
                validate_path_segment(run_id)
        except ValueError:
            body, status = error_response("Invalid project or run parameter", HTTPStatus.BAD_REQUEST, "INVALID_PARAM")
            return jsonify(body), status

        # Resolve by listing rather than joining: *project* is compared against
        # real entries and never concatenated onto *eval_dir*, so a hostile
        # value matches nothing instead of needing containment afterwards.
        # A miss here is "no such project", which is a 404 like any other.
        resolved_dir = resolve_child_dir(eval_dir, project)
        if resolved_dir is None:
            body, status = error_response("No runs found for project", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        project_dir = Path(resolved_dir)
        project = project_dir.name

        # Resolve run ID
        if not run_id or run_id == "latest":
            runs = list_runs(Path(eval_dir), project, limit=1)
            if not runs:
                body, status = error_response("No runs found for project", HTTPStatus.NOT_FOUND, "NOT_FOUND")
                return jsonify(body), status
            run_id = runs[0].run_id

        resolved_run_dir = resolve_child_dir(project_dir, run_id)
        if resolved_run_dir is None:
            body, status = error_response("Run data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        try:
            dimensions = read_run_data(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Run data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        dismissed = load_dismissed_keys(project_dir)
        deleted = load_deleted_keys(project_dir)

        # *dimensions* were read from this one run, so its directory is the
        # evidence basis for the rescore.
        result = rescore_dimensions(
            dimensions, dismissed, deleted, run_dir=Path(resolved_run_dir),
            rules=load_suppression_rules(project_dir))
        return jsonify(result)
