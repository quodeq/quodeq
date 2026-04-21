"""Admin/debug endpoints for the SQLite run index."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, current_app, jsonify

from quodeq.services import run_index as _run_index


def register_index_routes(app: Flask) -> None:
    """Register /api/index/* endpoints."""

    @app.post("/api/index/rebuild")
    def rebuild_index_endpoint() -> Response | tuple[Response, int]:
        provider = current_app.config.get("_provider")
        if provider is None or not hasattr(provider, "_open_index"):
            return jsonify({"error": "provider not available"}), HTTPStatus.SERVICE_UNAVAILABLE
        from quodeq.shared._env import get_evaluations_dir
        reports_root = Path(get_evaluations_dir())
        db = provider._open_index()
        try:
            count, elapsed_ms = _run_index.rebuild_index(db, reports_root)
        finally:
            db.close()
        return jsonify({"count": count, "elapsed_ms": elapsed_ms})
