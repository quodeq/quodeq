"""Create, update, delete, and duplicate routes for standards."""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)


def _handle_create(get_service, app: Flask) -> tuple[Response, int]:
    """Handle POST /api/standards -- create a new standard."""
    svc = get_service(app)
    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", 400, "bad_request")
    logger.info("standards.create id=%s", payload.get("id", "<unknown>"))
    try:
        detail = svc.create_standard(payload)
    except ValueError as exc:
        logger.debug("standards.create validation error: %s", exc)
        return error_response("Invalid standard data", 400, "bad_request")
    return jsonify(to_camel_dict(detail)), 201


def _handle_update(get_service, app: Flask, standard_id: str) -> Response:
    """Handle PUT /api/standards/<id> -- update a standard."""
    svc = get_service(app)
    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", 400, "bad_request")
    logger.info("standards.update id=%s", standard_id)
    try:
        detail = svc.update_standard(standard_id, payload)
    except FileNotFoundError:
        return error_response(f"Standard not found: {standard_id}", 404, "not_found")
    except PermissionError as exc:
        logger.warning("standards.update permission error: %s", exc)
        return error_response("Permission denied", 403, "forbidden")
    return jsonify(to_camel_dict(detail))


def _handle_delete(get_service, app: Flask, standard_id: str) -> tuple[str, int]:
    """Handle DELETE /api/standards/<id> -- delete a standard."""
    svc = get_service(app)
    logger.info("standards.delete id=%s", standard_id)
    try:
        svc.delete_standard(standard_id)
    except FileNotFoundError:
        return error_response(f"Standard not found: {standard_id}", 404, "not_found")
    except PermissionError as exc:
        logger.warning("standards.delete permission error: %s", exc)
        return error_response("Permission denied", 403, "forbidden")
    return "", 204


def _handle_duplicate(get_service, app: Flask, standard_id: str) -> tuple[Response, int]:
    """Handle POST /api/standards/<id>/duplicate -- duplicate a standard."""
    svc = get_service(app)
    payload = request.get_json(force=True)
    if not isinstance(payload, dict):
        return error_response("Request body must be a JSON object", 400, "bad_request")
    new_id = payload.get("newId") or payload.get("new_id")
    if not new_id:
        return error_response("newId is required", 400, "bad_request")
    logger.info("standards.duplicate id=%s new_id=%s", standard_id, new_id)
    try:
        detail = svc.duplicate_standard(standard_id, new_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.debug("standards.duplicate error: %s", exc)
        return error_response("Could not duplicate standard", 400, "bad_request")
    return jsonify(to_camel_dict(detail)), 201


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
