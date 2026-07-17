"""Routes for the shared results repository (config, status, refresh, publish).

Read-only invariant: no finding-mutation routes exist in this module or
anywhere under /api/shared/*.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.services.shared_publish import get_publish_status, start_publish
from quodeq.services.shared_repo import (
    ensure_shared_clone,
    last_synced_at,
    refresh_shared_clone,
    validate_remote_url,
)
from quodeq.services.shared_settings import (
    SharedSettings,
    read_settings,
    write_settings,
)
from quodeq.shared.validation import validate_path_segment

from .routes_common import reports_dir


def register_shared_routes(app: Flask) -> None:
    @app.get("/api/shared/status")
    def shared_status() -> Response:
        settings = read_settings()
        synced = last_synced_at(settings.url) if settings.url else None
        return jsonify(
            {
                "configured": settings.url is not None,
                "url": settings.url,
                "lastSynced": synced,
                "syncing": False,
                "publish": get_publish_status(),
            }
        )

    @app.put("/api/shared/config")
    def shared_config_put() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        url = str(body.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400
        try:
            validate_remote_url(url)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if ensure_shared_clone(url) is None:
            return (
                jsonify(
                    {"error": f"could not clone the repository, check that git can access {url}"}
                ),
                502,
            )
        write_settings(SharedSettings(url=url))
        return jsonify({"configured": True, "url": url})

    @app.delete("/api/shared/config")
    def shared_config_delete() -> Response:
        write_settings(SharedSettings(url=None))
        return jsonify({"configured": False})

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 400
        if not refresh_shared_clone(settings.url):
            return (
                jsonify({"stale": True, "lastSynced": last_synced_at(settings.url)}),
                502,
            )
        return jsonify({"stale": False, "lastSynced": last_synced_at(settings.url)})

    @app.post("/api/projects/<project>/publish")
    def shared_publish_start(project: str) -> tuple[Response, int]:
        try:
            validate_path_segment(project)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 400
        started = start_publish(
            project, settings.url, evaluations_root=Path(reports_dir())
        )
        if not started:
            return jsonify({"error": "a publish is already running"}), 409
        return jsonify({"started": True}), 202
