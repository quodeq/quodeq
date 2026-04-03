"""Create, update, delete, and duplicate routes for standards."""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)


def register_crud_routes(app: Flask, get_service) -> None:
    """Register create, update, delete, and duplicate routes for standards."""

    @app.post("/api/standards")
    def create_standard() -> tuple[Response, int]:
        svc = get_service(app)
        payload = request.get_json(force=True)
        logger.info("standards.create id=%s", payload.get("id", "<unknown>"))
        try:
            detail = svc.create_standard(payload)
        except ValueError as exc:
            return error_response(str(exc), 400, "bad_request")
        return jsonify(to_camel_dict(detail)), 201

    @app.put("/api/standards/<standard_id>")
    def update_standard(standard_id: str) -> Response:
        svc = get_service(app)
        payload = request.get_json(force=True)
        logger.info("standards.update id=%s", standard_id)
        try:
            detail = svc.update_standard(standard_id, payload)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        except PermissionError as exc:
            return error_response(str(exc), 403, "forbidden")
        return jsonify(to_camel_dict(detail))

    @app.delete("/api/standards/<standard_id>")
    def delete_standard(standard_id: str) -> tuple[str, int]:
        svc = get_service(app)
        logger.info("standards.delete id=%s", standard_id)
        try:
            svc.delete_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        except PermissionError as exc:
            return error_response(str(exc), 403, "forbidden")
        return "", 204

    @app.post("/api/standards/<standard_id>/duplicate")
    def duplicate_standard(standard_id: str) -> tuple[Response, int]:
        svc = get_service(app)
        payload = request.get_json(force=True)
        new_id = payload.get("newId") or payload.get("new_id")
        if not new_id:
            return error_response("newId is required", 400, "bad_request")
        logger.info("standards.duplicate id=%s new_id=%s", standard_id, new_id)
        try:
            detail = svc.duplicate_standard(standard_id, new_id)
        except (FileNotFoundError, ValueError) as exc:
            return error_response(str(exc), 400, "bad_request")
        return jsonify(to_camel_dict(detail)), 201
