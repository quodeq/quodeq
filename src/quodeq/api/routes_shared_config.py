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
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.validation import path_segment_error

from .helpers import json_error
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
                # can bind to it without existence checks. A reserved slot is
                # not an error response, so it carries no "code" (the
                # error-code gate exempts an "error" value of None).
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
            return json_error("url is required", 400, "URL_REQUIRED")
        outcome = connect_shared_repo(url, log=SHARED_LOG)
        if outcome.status == "invalid_url":
            return json_error(outcome.detail, 400, "INVALID_URL")
        if outcome.status == "clone_failed":
            return json_error(
                f"could not clone the repository, check that git can access {outcome.url}",
                502,
                "CLONE_FAILED",
            )
        if outcome.status == "foreign":
            return json_error(
                "the repository exists but does not look like a quodeq results repository",
                400,
                "FOREIGN_REPO",
            )
        if outcome.status == "unsupported_version":
            return json_error(
                "this shared repository requires a newer version of quodeq",
                400,
                "UNSUPPORTED_VERSION",
            )
        return jsonify({"configured": True, "url": outcome.url})

    @app.delete("/api/shared/config")
    def shared_config_delete() -> Response:
        # Ordering + locking business rule lives in
        # services/shared_repo.disconnect_shared_repo (Task 20).
        disconnect_shared_repo(log=SHARED_LOG)
        return jsonify({"configured": False})

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        settings = read_settings()
        if not settings.url:
            return json_error(
                "no shared repository configured", 400, "NO_SHARED_REPO"
            )
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
        err = path_segment_error(project)
        if err is not None:
            return json_error(err, 400, "INVALID_INPUT")
        settings = read_settings()
        if not settings.url:
            return json_error(
                "no shared repository configured", 400, "NO_SHARED_REPO"
            )
        outcome = _routes_shared.start_publish(
            project, settings.url, evaluations_root=Path(reports_dir())
        )
        if outcome == "already_running":
            return json_error("a publish is already running", 409, "PUBLISH_IN_PROGRESS")
        if outcome != "started":
            return json_error(
                "could not start the publish job, see server logs", 500, "PUBLISH_START_FAILED"
            )
        return jsonify({"started": True}), 202
