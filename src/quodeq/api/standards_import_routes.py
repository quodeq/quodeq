"""Import routes for the Standards Browser & Editor."""
from __future__ import annotations

import http.client
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify

from quodeq.api._constants import ERROR_CODE_BAD_REQUEST, ERROR_CODE_CONFLICT, ERROR_CODE_FORBIDDEN
from quodeq.api.helpers import json_object_or_error, sanitize_for_log, error_response
from quodeq.services.import_validator import StandardImportValidationError
from quodeq.services.standards import IMPORT_STATUS_CONFLICT
from quodeq.services.standards_library import StandardImportConflictError
from quodeq.shared.serialization import to_camel_dict

logger = logging.getLogger(__name__)


def _do_import_from_library(app: Flask, get_library_client) -> tuple[Response, int]:
    library = get_library_client(app)
    if library is None:
        return error_response("Standards library not configured", HTTPStatus.BAD_REQUEST, "library_not_configured")
    payload = json_object_or_error()
    if not isinstance(payload, dict):
        return payload
    file_path = payload.get("file")
    if not file_path:
        return error_response("file is required", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    if not isinstance(file_path, str):
        # A non-string truthy value (5, a list) passed the check above and
        # made the containment test below raise TypeError, a bare 500.
        return error_response("file must be a string", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    if ".." in file_path or file_path.startswith("/"):
        return error_response("Invalid file path", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    try:
        library.import_standard(file_path, Path(app.config["STANDARDS_EVALUATORS_DIR"]))
    except StandardImportConflictError as exc:
        logger.warning("Library import conflict: %s", exc)
        # A hand-written resolution hint, not `str(exc)`: this module never
        # echoes caught-exception text into a response (see
        # tests/api/test_no_exception_echo.py). The generic "Import
        # conflict" gave the caller no path forward; this names one.
        return error_response(
            "A standard with this ID already exists from a different source. "
            "Duplicate it to customize your own copy, or delete the existing one, then retry.",
            HTTPStatus.CONFLICT, ERROR_CODE_CONFLICT,
        )
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # See list_library: HTTPException is urllib's truncated/malformed
        # response family and is not an OSError.
        logger.warning("Library import failed: %s", exc)
        return error_response(
            "Import from library failed. Check that the library server is reachable and the standard file is valid.",
            HTTPStatus.BAD_GATEWAY, "import_error",
        )
    logger.info("standards.import_from_library file=%s", sanitize_for_log(file_path))
    return jsonify({"status": "imported"}), HTTPStatus.CREATED


def _validate_import_body(body):
    """Split an import request body into (data, force, error_response).

    *body* is whatever ``json_object_or_error`` returned, so a non-dict is
    already that helper's error response and is passed straight back.
    """
    if not isinstance(body, dict):
        return None, None, body
    data = body.get("data")
    if not data or not isinstance(data, dict):
        return None, None, error_response(
            "'data' field is required and must be an object",
            HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST,
        )
    return data, body.get("force", False), None


def _do_import_standard(app: Flask, get_service) -> tuple[Response, int]:
    svc = get_service(app)
    data, force, err = _validate_import_body(json_object_or_error())
    if err is not None:
        return err
    imported_id = data.get("id", "<unknown>")
    logger.info("standards.import id=%s", sanitize_for_log(str(imported_id)))
    try:
        result = svc.import_from_file(data, force=force)
    except StandardImportValidationError as exc:
        # The validator's own field-level reasons, carried on the error
        # itself. Re-running validate_import in this handler reported every
        # ValueError raised AFTER validation passed (scan_injection, a
        # corrupt existing file) as "schema validation failed".
        # ``public_message`` is the hand-written text, not str(exc): this
        # module never echoes caught-exception text into a response (see
        # tests/api/test_no_exception_echo.py).
        logger.warning("standards.import validation error: %s", exc)
        return error_response(
            f"Invalid import data for standard {imported_id!r}: {exc.public_message}",
            HTTPStatus.BAD_REQUEST, "validation_error",
        )
    except ValueError as exc:
        # Anything else that went wrong after validation passed: a fixed,
        # generic message, with the reason only in the log.
        logger.warning("standards.import failed: %s", exc)
        return error_response(
            f"Could not import standard {imported_id!r}. Check the standard file and the "
            "existing standard with that id, then retry.",
            HTTPStatus.BAD_REQUEST, "import_error",
        )
    except PermissionError as exc:
        logger.warning("standards.import permission error: %s", exc)
        return error_response("Permission denied", HTTPStatus.FORBIDDEN, ERROR_CODE_FORBIDDEN)
    if result["status"] == IMPORT_STATUS_CONFLICT:
        return jsonify({
            "status": IMPORT_STATUS_CONFLICT,
            "existing": to_camel_dict(result["existing"]),
            "warnings": result["warnings"],
        }), HTTPStatus.CONFLICT
    return jsonify({
        "status": "imported",
        "detail": to_camel_dict(result["detail"]),
        "warnings": result["warnings"],
    }), HTTPStatus.CREATED


def register_import_routes(app: Flask, get_service, get_library_client) -> None:
    """Register import and library routes for the standards API."""

    @app.post("/api/standards/library/import")
    def import_from_library() -> tuple[Response, int]:
        return _do_import_from_library(app, get_library_client)

    @app.post("/api/standards/import")
    def import_standard() -> tuple[Response, int]:
        return _do_import_standard(app, get_service)
