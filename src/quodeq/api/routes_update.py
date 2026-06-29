"""/api/update/* routes — notify-only update status, manual check, dismiss, settings."""

from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.update.checker import check_async, dismiss, get_status, run_check, set_settings


def register_update_routes(app: Flask) -> None:
    """Register the /api/update/* endpoints."""

    @app.get("/api/update/status")
    def update_status() -> Response:
        check_async()  # throttled + non-blocking; refreshes state for next time
        return jsonify(get_status())

    @app.post("/api/update/check")
    def update_check() -> Response:
        run_check(force=True)
        return jsonify(get_status())

    @app.post("/api/update/dismiss")
    def update_dismiss() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        version = body.get("version")
        if not version:
            return jsonify({"error": "version is required", "code": "MISSING_PARAM"}), 400
        dismiss(version)
        return jsonify({"ok": True, "status": get_status()})

    @app.post("/api/update/settings")
    def update_settings() -> Response:
        body = request.get_json(silent=True) or {}
        set_settings(
            auto_check_enabled=body.get("auto_check_enabled"),
            disclosed=body.get("disclosed"),
        )
        return jsonify({"ok": True, "status": get_status()})
