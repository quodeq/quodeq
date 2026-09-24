"""Config/status/lifecycle routes for the shared results repository.

Split out of routes_shared.py: status, config PUT/DELETE, refresh,
and the local project-publish route.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.services.shared_connect import ConnectStatus, connect_shared_repo
from quodeq.services.shared_publish import PublishStartResult, get_publish_status
from quodeq.services.shared_repo import RepoFormat, disconnect_shared_repo, last_synced_at, read_state
from quodeq.services.shared_settings import read_settings
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.validation import path_segment_error

from .helpers import json_error
from .routes_common import reports_dir


def shared_status() -> Response:
    """Report the shared repo connection, last sync, clone health and publish progress.

    One call backs the whole Shared tab header, so the UI does not have to
    infer "healthy but never published into" from configured + lastSynced.
    """
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


def shared_config_put() -> Response | tuple[Response, int]:
    """Connect to the shared results repository at the posted ``url``.

    Clones it and verifies it is a quodeq results repo before accepting, so a
    typo or a foreign repository fails here rather than on the first publish.
    """
    body = request.get_json(silent=True) or {}
    url = str(body.get("url") or "").strip()
    if not url:
        return json_error("url is required", 400, "URL_REQUIRED")
    outcome = connect_shared_repo(url, log=SHARED_LOG)
    if outcome.status == ConnectStatus.INVALID_URL:
        return json_error(outcome.detail, 400, "INVALID_URL")
    if outcome.status == ConnectStatus.CLONE_FAILED:
        return json_error(
            f"could not clone the repository, check that git can access {outcome.url}",
            502,
            "CLONE_FAILED",
        )
    if outcome.status == RepoFormat.FOREIGN:
        return json_error(
            "the repository exists but does not look like a quodeq results repository",
            400,
            "FOREIGN_REPO",
        )
    if outcome.status == RepoFormat.UNSUPPORTED_VERSION:
        return json_error(
            "this shared repository requires a newer version of quodeq",
            400,
            "UNSUPPORTED_VERSION",
        )
    return jsonify({"configured": True, "url": outcome.url})


def shared_config_delete() -> Response:
    """Disconnect from the shared repository and drop the local clone."""
    # Ordering + locking business rule lives in
    # services/shared_repo.disconnect_shared_repo.
    disconnect_shared_repo(log=SHARED_LOG)
    return jsonify({"configured": False})


def _shared_refresh(refresh_clone: Callable[[str], tuple[bool, str | None]]) -> Response | tuple[Response, int]:
    settings = read_settings()
    if not settings.url:
        return json_error(
            "no shared repository configured", 400, "NO_SHARED_REPO"
        )
    ok, reason = refresh_clone(settings.url)
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


def _shared_publish_start(project: str, start_publish: Callable[..., str]) -> tuple[Response, int]:
    err = path_segment_error(project)
    if err is not None:
        return json_error(err, 400, "INVALID_INPUT")
    settings = read_settings()
    if not settings.url:
        return json_error(
            "no shared repository configured", 400, "NO_SHARED_REPO"
        )
    outcome = start_publish(project, settings.url, evaluations_root=Path(reports_dir()))
    if outcome == PublishStartResult.ALREADY_RUNNING:
        return json_error("a publish is already running", 409, "PUBLISH_IN_PROGRESS")
    if outcome != PublishStartResult.STARTED:
        return json_error(
            "could not start the publish job, see server logs", 500, "PUBLISH_START_FAILED"
        )
    return jsonify({"started": True}), 202


def register_shared_config_routes(app: Flask) -> None:
    """Bind the shared-repo status, config, refresh and publish routes."""
    # refresh_shared_clone and start_publish are looked up on the
    # quodeq.api.routes_shared facade at call time (rather than imported
    # directly here) so that tests patching
    # "quodeq.api.routes_shared.refresh_shared_clone" /
    # "...start_publish" keep working after the split.
    from quodeq.api import routes_shared as _routes_shared

    app.get("/api/shared/status")(shared_status)
    app.put("/api/shared/config")(shared_config_put)
    app.delete("/api/shared/config")(shared_config_delete)

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        return _shared_refresh(_routes_shared.refresh_shared_clone)

    @app.post("/api/projects/<project>/publish")
    def shared_publish_start(project: str) -> tuple[Response, int]:
        return _shared_publish_start(project, _routes_shared.start_publish)
