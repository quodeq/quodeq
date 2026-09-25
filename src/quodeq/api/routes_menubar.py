"""/api/menubar routes — the Settings toggle for the built-in menu bar icon."""

from __future__ import annotations

from http import HTTPStatus

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_MISSING_PARAM
from quodeq.api.helpers import json_error, optional_json_object_or_response
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
        body = optional_json_object_or_response(CODE_MISSING_PARAM)
        if not isinstance(body, dict):
            return body
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            return json_error("enabled must be a boolean", HTTPStatus.BAD_REQUEST, CODE_MISSING_PARAM)
        set_enabled(enabled)
        if enabled:
            control.spawn()
        else:
            control.stop()
        return jsonify(_status())
