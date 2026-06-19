"""Admin/debug endpoints for the SQLite run index."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response, current_app, jsonify

from quodeq.api.helpers import error_response

_logger = logging.getLogger(__name__)


def register_index_routes(app: Flask) -> None:
    """Register /api/index/* endpoints."""

    @app.post("/api/index/rebuild")
    def rebuild_index_endpoint() -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        if provider is None or not hasattr(provider, "rebuild_index"):
            return jsonify({"error": "provider not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        try:
            count, elapsed_ms = provider.rebuild_index()
        except Exception:
            _logger.exception("Unexpected error rebuilding index")
            body, status = error_response("Failed to rebuild index", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR")
            return jsonify(body), status
        return jsonify({"count": count, "elapsed_ms": elapsed_ms})
