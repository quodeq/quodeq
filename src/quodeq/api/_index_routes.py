"""Admin/debug endpoints for the SQLite run index."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, current_app, jsonify


def register_index_routes(app: Flask) -> None:
    """Register /api/index/* endpoints."""

    @app.post("/api/index/rebuild")
    def rebuild_index_endpoint() -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        if provider is None or not hasattr(provider, "rebuild_index"):
            return jsonify({"error": "provider not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        count, elapsed_ms = provider.rebuild_index()
        return jsonify({"count": count, "elapsed_ms": elapsed_ms})
