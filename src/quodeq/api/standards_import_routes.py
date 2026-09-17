"""Import routes for the Standards Browser & Editor."""
from __future__ import annotations

import http.client
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import ERROR_CODE_BAD_REQUEST, ERROR_CODE_FORBIDDEN
from quodeq.api.helpers import _sanitize_for_log, error_response
from quodeq.services.standards_library import StandardImportConflictError
from quodeq.shared.serialization import to_camel_dict

logger = logging.getLogger(__name__)


def _json_object_body() -> dict | None:
    """Return the request's JSON body when it is an object, else None."""
    payload = request.get_json(force=True)
    return payload if isinstance(payload, dict) else None


def _body_not_object() -> tuple[Response, int]:
    return error_response("Request body must be a JSON object", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)


def _do_import_from_library(app: Flask, get_library_client) -> tuple[Response, int]:
    library = get_library_client(app)
    if library is None:
        return error_response("Standards library not configured", HTTPStatus.BAD_REQUEST, "library_not_configured")
    payload = _json_object_body()
    if payload is None:
        return _body_not_object()
    file_path = payload.get("file")
    if not file_path:
        return error_response("file is required", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    if ".." in file_path or file_path.startswith("/"):
        return error_response("Invalid file path", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    try:
        library.import_standard(file_path, Path(app.config["STANDARDS_EVALUATORS_DIR"]))
    except StandardImportConflictError as exc:
        logger.warning("Library import conflict: %s", exc)
        return error_response("Import conflict", 409, "conflict")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # See list_library: HTTPException is urllib's truncated/malformed
        # response family and is not an OSError.
        logger.warning("Library import failed: %s", exc)
        return error_response(
            "Import from library failed. Check that the library server is reachable and the standard file is valid.",
            502, "import_error",
        )
    logger.info("standards.import_from_library file=%s", _sanitize_for_log(file_path))
    return jsonify({"status": "imported"}), 201


def _do_import_standard(app: Flask, get_service) -> tuple[Response, int]:
    svc = get_service(app)
    payload = _json_object_body()
    if payload is None:
        return _body_not_object()
    data = payload.get("data")
    if not data or not isinstance(data, dict):
        return error_response("'data' field is required and must be an object", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    force = payload.get("force", False)
    logger.info("standards.import id=%s", _sanitize_for_log(str(data.get("id", "<unknown>"))))
    try:
        result = svc.import_from_file(data, force=force)
    except ValueError as exc:
        logger.warning("standards.import validation error: %s", exc)
        return error_response("Invalid import data", HTTPStatus.BAD_REQUEST, "validation_error")
    except PermissionError as exc:
        logger.warning("standards.import permission error: %s", exc)
        return error_response("Permission denied", HTTPStatus.FORBIDDEN, ERROR_CODE_FORBIDDEN)
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


def register_import_routes(app: Flask, get_service, get_library_client) -> None:
    """Register import and library routes for the standards API."""

    @app.post("/api/standards/library/import")
    def import_from_library() -> tuple[Response, int]:
        return _do_import_from_library(app, get_library_client)

    @app.post("/api/standards/import")
    def import_standard() -> tuple[Response, int]:
        return _do_import_standard(app, get_service)
