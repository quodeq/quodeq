"""/api/menubar routes — the Settings toggle for the built-in menu bar icon."""

from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.menubar import control
from quodeq.menubar.state import is_enabled, set_enabled


def _status() -> dict:
    return {
        "supported": control.is_supported(),
        "enabled": is_enabled(),
        "running": control.is_running(),
    }


def register_menubar_routes(app: Flask) -> None:
    """Register the /api/menubar endpoints."""

    @app.get("/api/menubar")
    def menubar_status() -> Response:
        return jsonify(_status())

    @app.put("/api/menubar")
    def menubar_set() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "enabled must be a boolean", "code": "MISSING_PARAM"}), 400
        set_enabled(enabled)
        if enabled:
            control.spawn()
        else:
            control.stop()
        return jsonify(_status())
