"""Create, update, delete, and duplicate routes for standards."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response, jsonify

from quodeq.api._constants import ERROR_CODE_BAD_REQUEST, ERROR_CODE_FORBIDDEN, ERROR_CODE_NOT_FOUND
from quodeq.api.helpers import error_response, json_object_or_error
from quodeq.services.ports import StandardNotFoundError, StandardProtectedError
from quodeq.shared.serialization import to_camel_dict

logger = logging.getLogger(__name__)


def _handle_create(get_service, app: Flask) -> tuple[Response, int]:
    """Handle POST /api/standards -- create a new standard."""
    svc = get_service(app)
    payload = json_object_or_error()
    if not isinstance(payload, dict):
        return payload
    standard_id = payload.get("id")
    if not isinstance(standard_id, str) or not standard_id:
        # create_standard reads data["id"] and tests `"/" in standard_id`,
        # so a missing id raised KeyError and a non-string id TypeError --
        # both 500s -- before its own ValueError could answer 400.
        return error_response(
            "id must be a non-empty string", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST,
        )
    logger.info("standards.create id=%s", standard_id)
    try:
        detail = svc.create_standard(payload)
    except ValueError as exc:
        # create_standard raises ValueError for exactly two reasons: an
        # invalid id (contains '/', '\\', '..') or an id that's already in
        # use. Name the id from `payload` (not from `exc`) -- this module
        # never echoes caught-exception text into a response, see
        # tests/api/test_no_exception_echo.py.
        logger.debug("standards.create validation error: %s", exc)
        return error_response(
            f"Invalid standard data: standard id {standard_id!r} is invalid, or already exists",
            HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST,
        )
    return jsonify(to_camel_dict(detail)), HTTPStatus.CREATED


def _store_error_response(exc: Exception, standard_id: str, operation: str) -> Response:
    """The response for a store error the update/delete of a standard raised.

    A missing standard is a 404; a permission error is logged under
    ``standards.<operation>`` and answered with a 403.
    """
    if isinstance(exc, StandardNotFoundError):
        return error_response(f"Standard not found: {standard_id}", HTTPStatus.NOT_FOUND, ERROR_CODE_NOT_FOUND)
    logger.warning("standards.%s permission error: %s", operation, exc)
    return error_response("Permission denied", HTTPStatus.FORBIDDEN, ERROR_CODE_FORBIDDEN)


def _handle_update(get_service, app: Flask, standard_id: str) -> Response:
    """Handle PUT /api/standards/<id> -- update a standard."""
    svc = get_service(app)
    payload = json_object_or_error(ERROR_CODE_BAD_REQUEST)
    if not isinstance(payload, dict):
        return payload
    logger.info("standards.update id=%s", standard_id)
    try:
        detail = svc.update_standard(standard_id, payload)
    except (StandardNotFoundError, StandardProtectedError) as exc:
        return _store_error_response(exc, standard_id, "update")
    except ValueError:
        return error_response(f"Invalid standard id: {standard_id!r}", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    return jsonify(to_camel_dict(detail))


def _handle_delete(get_service, app: Flask, standard_id: str) -> tuple[str, int]:
    """Handle DELETE /api/standards/<id> -- delete a standard."""
    svc = get_service(app)
    logger.info("standards.delete id=%s", standard_id)
    try:
        svc.delete_standard(standard_id)
    except (StandardNotFoundError, StandardProtectedError) as exc:
        return _store_error_response(exc, standard_id, "delete")
    except ValueError:
        return error_response(f"Invalid standard id: {standard_id!r}", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    return "", HTTPStatus.NO_CONTENT


def _handle_duplicate(get_service, app: Flask, standard_id: str) -> tuple[Response, int]:
    """Handle POST /api/standards/<id>/duplicate -- duplicate a standard."""
    svc = get_service(app)
    payload = json_object_or_error(ERROR_CODE_BAD_REQUEST)
    if not isinstance(payload, dict):
        return payload
    new_id = payload.get("newId") or payload.get("new_id")
    if not isinstance(new_id, str) or not new_id:
        return error_response("newId must be a non-empty string", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    logger.info("standards.duplicate id=%s new_id=%s", standard_id, new_id)
    try:
        detail = svc.duplicate_standard(standard_id, new_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.debug("standards.duplicate error: %s", exc)
        return error_response("Could not duplicate standard", HTTPStatus.BAD_REQUEST, ERROR_CODE_BAD_REQUEST)
    return jsonify(to_camel_dict(detail)), HTTPStatus.CREATED


def register_crud_routes(app: Flask, get_service) -> None:
    """Register create, update, delete, and duplicate routes for standards."""

    @app.post("/api/standards")
    def create_standard() -> tuple[Response, int]:
        return _handle_create(get_service, app)

    @app.put("/api/standards/<standard_id>")
    def update_standard(standard_id: str) -> Response:
        return _handle_update(get_service, app, standard_id)

    @app.delete("/api/standards/<standard_id>")
    def delete_standard(standard_id: str) -> tuple[str, int]:
        return _handle_delete(get_service, app, standard_id)

    @app.post("/api/standards/<standard_id>/duplicate")
    def duplicate_standard(standard_id: str) -> tuple[Response, int]:
        return _handle_duplicate(get_service, app, standard_id)
