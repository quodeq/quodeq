"""Admin/debug endpoints for the SQLite run index."""
from __future__ import annotations

import logging
import sqlite3
from http import HTTPStatus

from flask import Flask, Response, current_app, jsonify

from quodeq.api._constants import CODE_INTERNAL_ERROR
from quodeq.api.helpers import json_error

_logger = logging.getLogger(__name__)


def register_index_routes(app: Flask) -> None:
    """Register /api/index/* endpoints."""

    @app.post("/api/index/rebuild")
    def rebuild_index_endpoint() -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        if provider is None or not hasattr(provider, "rebuild_index"):
            return json_error("provider not available", HTTPStatus.SERVICE_UNAVAILABLE, "PROVIDER_UNAVAILABLE")
        try:
            count, elapsed_ms = provider.rebuild_index()
        except (sqlite3.Error, OSError):
            _logger.exception("Unexpected error rebuilding index")
            return json_error("Failed to rebuild index", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_INTERNAL_ERROR)
        return jsonify({"count": count, "elapsed_ms": elapsed_ms})
