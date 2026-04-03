"""API routes for dismissing and restoring individual findings."""
from __future__ import annotations

import importlib
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.services.dismissed import dismiss_finding, load_dismissed, restore_finding, restore_all_findings


def _project_dir(evaluations_dir: str, project: str) -> Path:
    base = Path(evaluations_dir).resolve()
    resolved = (base / project).resolve()
    if not resolved.is_relative_to(base):
        from flask import abort
        abort(400, description="Invalid project path")
    return resolved


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    def _eval_dir() -> str:
        return app.config.get("EVALUATIONS_DIR") or importlib.import_module("quodeq.shared.utils").get_evaluations_dir()

    @app.get("/api/findings/dismissed")
    def list_dismissed() -> Response:
        project = request.args.get("project", "")
        if not project:
            return jsonify([])
        return jsonify(load_dismissed(_project_dir(_eval_dir(), project)))

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        dismiss_finding(_project_dir(_eval_dir(), project), body)
        return jsonify({"ok": True}), 200

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        restore_finding(_project_dir(_eval_dir(), project), body)
        return jsonify({"ok": True}), 200

    @app.post("/api/findings/restore-all")
    def restore_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        if not project:
            return jsonify({"error": "project is required"}), 400
        count = restore_all_findings(_project_dir(_eval_dir(), project))
        return jsonify({"ok": True, "restored": count}), 200
