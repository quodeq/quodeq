"""Config/status/lifecycle routes for the shared results repository.

Split out of routes_shared.py (Task 9): status, config PUT/DELETE, refresh,
and the local project-publish route.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.services.shared_connect import connect_shared_repo
from quodeq.services.shared_publish import get_publish_status
from quodeq.services.shared_repo import disconnect_shared_repo, last_synced_at, read_state
from quodeq.services.shared_settings import read_settings
from quodeq.shared.validation import validate_path_segment

from .helpers import error_response
from .routes_common import reports_dir


def register_shared_config_routes(app: Flask) -> None:
    # refresh_shared_clone and start_publish are looked up on the
    # quodeq.api.routes_shared facade at call time (rather than imported
    # directly here) so that tests patching
    # "quodeq.api.routes_shared.refresh_shared_clone" /
    # "...start_publish" keep working after the split.
    from quodeq.api import routes_shared as _routes_shared

    @app.get("/api/shared/status")
    def shared_status() -> Response:
        settings = read_settings()
        synced = last_synced_at(settings.url) if settings.url else None
        # The wire shape is camelCase throughout; the publish status dict is
        # a service-internal snake_case structure, so rename at the boundary.
        publish = get_publish_status()
        publish["finishedAt"] = publish.pop("finished_at", None)
        return jsonify(
            {
                "configured": settings.url is not None,
                "url": settings.url,
                "lastSynced": synced,
                "syncing": False,
                # Reserved for sync-level failures; always present so the UI
                # can bind to it without existence checks.
                "error": None,
                "publish": publish,
                # ok | empty | foreign | unsupported_version | missing | None
                # (unconfigured) -- lets the UI distinguish "healthy but
                # never published into" from the failure states instead of
                # inferring clone health from configured+lastSynced alone.
                "repoState": read_state(settings.url) if settings.url else None,
            }
        )

    @app.put("/api/shared/config")
    def shared_config_put() -> Response | tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        url = str(body.get("url") or "").strip()
        if not url:
            body, status = error_response("url is required", 400, "URL_REQUIRED")
            return jsonify(body), status
        outcome = connect_shared_repo(url)
        if outcome.status == "invalid_url":
            return jsonify({"error": outcome.detail}), 400
        if outcome.status == "clone_failed":
            body, status = error_response(
                f"could not clone the repository, check that git can access {outcome.url}",
                502,
                "CLONE_FAILED",
            )
            return jsonify(body), status
        if outcome.status == "foreign":
            body, status = error_response(
                "the repository exists but does not look like a quodeq results repository",
                400,
                "FOREIGN_REPO",
            )
            return jsonify(body), status
        if outcome.status == "unsupported_version":
            body, status = error_response(
                "this shared repository requires a newer version of quodeq",
                400,
                "UNSUPPORTED_VERSION",
            )
            return jsonify(body), status
        return jsonify({"configured": True, "url": outcome.url})

    @app.delete("/api/shared/config")
    def shared_config_delete() -> Response:
        # Ordering + locking business rule lives in
        # services/shared_repo.disconnect_shared_repo (Task 20).
        disconnect_shared_repo()
        return jsonify({"configured": False})

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        settings = read_settings()
        if not settings.url:
            return jsonify({"error": "no shared repository configured"}), 400
        ok, reason = _routes_shared.refresh_shared_clone(settings.url)
        if not ok:
            return (
                jsonify(
                    {
                        "stale": True,
                        "lastSynced": last_synced_at(settings.url),
                        "error": reason,
                        "code": "REFRESH_FAILED",
                    }
                ),
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
        outcome = _routes_shared.start_publish(
            project, settings.url, evaluations_root=Path(reports_dir())
        )
        if outcome == "already_running":
            body, status = error_response("a publish is already running", 409, "PUBLISH_IN_PROGRESS")
            return jsonify(body), status
        if outcome != "started":
            body, status = error_response(
                "could not start the publish job, see server logs", 500, "PUBLISH_START_FAILED"
            )
            return jsonify(body), status
        return jsonify({"started": True}), 202
