"""API routes for the Standards Browser & Editor."""
from __future__ import annotations
import logging
from pathlib import Path
from flask import Flask, Response, jsonify, request
from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict
from quodeq.services.standards import StandardsService

logger = logging.getLogger(__name__)

def _get_service(app: Flask) -> StandardsService:
    if not hasattr(app, "_standards_service"):
        app._standards_service = StandardsService(
            evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
            compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
            dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        )
    return app._standards_service

def register_standards_routes(app: Flask) -> None:
    @app.get("/api/standards")
    def list_standards() -> Response:
        svc = _get_service(app)
        return jsonify([to_camel_dict(s) for s in svc.list_standards()])

    @app.get("/api/standards/<standard_id>")
    def get_standard(standard_id: str) -> Response:
        svc = _get_service(app)
        try:
            detail = svc.get_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        return jsonify(to_camel_dict(detail))
