"""Import routes for the Standards Browser & Editor."""
from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)


def register_import_routes(app: Flask, get_service, get_library_client) -> None:
    """Register import and library routes for the standards API."""

    @app.post("/api/standards/library/import")
    def import_from_library() -> tuple[Response, int]:
        library = get_library_client(app)
        if library is None:
            return error_response("Standards library not configured", 400, "library_not_configured")
        payload = request.get_json(force=True)
        file_path = payload.get("file")
        if not file_path:
            return error_response("file is required", 400, "bad_request")
        try:
            library.import_standard(file_path, Path(app.config["STANDARDS_EVALUATORS_DIR"]))
        except ValueError as exc:
            return error_response(str(exc), 409, "conflict")
        except Exception as exc:
            logger.warning("Library import failed: %s", exc)
            return error_response("Import from library failed", 502, "import_error")
        logger.info("standards.import_from_library file=%s", file_path)
        return jsonify({"status": "imported"}), 201

    @app.post("/api/standards/import")
    def import_standard() -> tuple[Response, int]:
        svc = get_service(app)
        payload = request.get_json(force=True)
        data = payload.get("data")
        if not data or not isinstance(data, dict):
            return error_response("'data' field is required and must be an object", 400, "bad_request")
        force = payload.get("force", False)
        logger.info("standards.import id=%s", data.get("id", "<unknown>"))
        try:
            result = svc.import_from_file(data, force=force)
        except ValueError as exc:
            return error_response(str(exc), 400, "validation_error")
        except PermissionError as exc:
            return error_response(str(exc), 403, "forbidden")
        if result["status"] == "conflict":
            return jsonify({
                "status": "conflict",
                "existing": to_camel_dict(result["existing"]),
                "warnings": result["warnings"],
            }), 409
        return jsonify({
            "status": "imported",
            "detail": to_camel_dict(result["detail"]),
            "warnings": result["warnings"],
        }), 201
