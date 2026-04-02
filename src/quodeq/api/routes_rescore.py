"""API route for live rescoring after dismissals."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.data.fs.report_parser.runs import read_run_data
from quodeq.services.ports import list_runs
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys
from quodeq.services.rescore import rescore_dimensions


def _eval_dir_from_app(app: Flask) -> str:
    return app.config.get("EVALUATIONS_DIR") or __import__(
        "quodeq.shared.utils", fromlist=["get_evaluations_dir"]
    ).get_evaluations_dir()


def register_rescore_routes(app: Flask) -> None:
    """Register /api/rescore route."""

    @app.get("/api/rescore")
    def rescore() -> Response | tuple[Response, int]:
        project = request.args.get("project", "")
        if not project:
            return jsonify({"error": "project query parameter is required"}), 400

        run_id = request.args.get("run", "")
        eval_dir = _eval_dir_from_app(app)

        # Resolve run ID
        if not run_id or run_id == "latest":
            runs = list_runs(Path(eval_dir), project, limit=1)
            if not runs:
                return jsonify({"error": "No runs found for project"}), 404
            run_id = runs[0].run_id

        try:
            dimensions = read_run_data(Path(eval_dir), project, run_id)
        except FileNotFoundError:
            return jsonify({"error": "Run data not found"}), 404

        project_dir = Path(eval_dir) / project
        dismissed = load_dismissed_keys(project_dir)

        result = rescore_dimensions(dimensions, dismissed)
        return jsonify(result)
