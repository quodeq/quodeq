"""GET routes for the Standards Browser & Editor."""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify

from quodeq.api.helpers import error_response
from quodeq.core.types import to_camel_dict

logger = logging.getLogger(__name__)


def register_read_routes(app: Flask, get_service, get_library_client) -> None:
    """Register GET routes for the standards API."""

    @app.get("/api/standards/refs/cwe")
    def list_cwes() -> Response:
        if not hasattr(app, "_cwe_list"):
            app._cwe_list = get_service(app).load_cwe_list()
        return jsonify(app._cwe_list)

    @app.get("/api/standards")
    def list_standards() -> Response:
        svc = get_service(app)
        return jsonify([to_camel_dict(s) for s in svc.list_standards()])

    @app.get("/api/standards/library")
    def list_library() -> Response:
        library = get_library_client(app)
        if library is None:
            return jsonify([])
        try:
            index = library.fetch_index()
        except Exception as exc:
            logger.warning("Failed to fetch library index: %s", exc)
            return error_response("Failed to connect to standards library", 502, "library_error")
        return jsonify(index)

    @app.get("/api/standards/<standard_id>")
    def get_standard(standard_id: str) -> Response:
        svc = get_service(app)
        try:
            detail = svc.get_standard(standard_id)
        except FileNotFoundError:
            return error_response(f"Standard not found: {standard_id}", 404, "not_found")
        return jsonify(to_camel_dict(detail))
