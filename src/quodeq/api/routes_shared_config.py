"""Config/status/lifecycle routes for the shared results repository.

Status, config PUT/DELETE, refresh, and the local project-publish route.
``refresh_shared_clone``, ``start_publish`` and ``start_connect`` are
imported directly from their real owner, never through the ``routes_shared``
facade, so this module never imports back a sibling that imports it. Tests
patch "quodeq.api.routes_shared_config.refresh_shared_clone" /
"...start_publish" / "...start_connect".
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_INPUT, QUERY_FLAG_TRUE
from quodeq.api.routes_github_access import access_failure_response
from quodeq.services.github_access import resolve_access
from quodeq.services.shared_connect_job import (
    ConnectStartResult,
    get_connect_status,
    is_connect_running,
    start_connect,
    url_failure,
)
from quodeq.services.shared_publish import PublishStartResult, get_publish_status, start_publish
from quodeq.services.shared_repo import (
    disconnect_shared_repo,
    last_synced_at,
    read_state,
    refresh_shared_clone,
)
from quodeq.services.shared_settings import read_settings
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.validation import path_segment_error

from ._url_body import required_url_or_error
from .helpers import json_error
from .routes_common import reports_dir
from .routes_shared_common import no_shared_repo_error

CODE_CONNECT_IN_PROGRESS = "CONNECT_IN_PROGRESS"
CODE_CONNECT_START_FAILED = "CONNECT_START_FAILED"
CODE_CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
MESSAGE_CONNECT_IN_PROGRESS = "a connect is already running"


def shared_status() -> Response:
    """Report the shared repo connection, last sync, clone health and job progress.

    One call backs the whole Shared tab header, so the UI does not have to
    infer "healthy but never published into" from configured + lastSynced.
    """
    settings = read_settings()
    synced = last_synced_at(settings.url) if settings.url else None
    # The wire shape is camelCase throughout; the publish and connect status
    # dicts are service-internal snake_case structures, so rename at the boundary.
    publish = get_publish_status()
    publish["finishedAt"] = publish.pop("finished_at", None)
    connect = get_connect_status()
    connect["finishedAt"] = connect.pop("finished_at", None)
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
            "connect": connect,
            # ok | empty | foreign | unsupported_version | missing | None
            # (unconfigured) -- lets the UI distinguish "healthy but
            # never published into" from the failure states instead of
            # inferring clone health from configured+lastSynced alone.
            "repoState": read_state(settings.url) if settings.url else None,
        }
    )


def shared_config_put() -> Response | tuple[Response, int]:
    """Start connecting to the shared results repository at the posted ``url``.

    A malformed URL fails here with 400. Otherwise the clone and the format
    check run as a background job and this answers 202; the outcome is
    reported under ``connect`` in GET /api/shared/status.
    """
    url = required_url_or_error()
    if not isinstance(url, str):
        return url
    failure = url_failure(url)
    if failure is not None:
        return json_error(failure.message, failure.http_status, failure.code)
    access = resolve_access(url)
    if not access.reachable:
        return access_failure_response(access)
    # clone_url is ignored: the clone dir is keyed by the configured URL, so an ssh
    # results-repo URL only works with the user's own SSH setup in v1.
    outcome = start_connect(url, log=SHARED_LOG, env=access.env)
    if outcome == ConnectStartResult.ALREADY_RUNNING:
        return json_error(MESSAGE_CONNECT_IN_PROGRESS, HTTPStatus.CONFLICT, CODE_CONNECT_IN_PROGRESS)
    if outcome != ConnectStartResult.STARTED:
        return json_error(
            "could not start the connect job, see server logs",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            CODE_CONNECT_START_FAILED,
        )
    return jsonify({"started": True, "url": url}), HTTPStatus.ACCEPTED


def shared_config_delete() -> Response | tuple[Response, int]:
    """Disconnect from the shared repository and drop the local clone.

    The clone is deleted from disk, so the caller must pass ``?confirm=true``
    (same gate as the other destructive DELETEs). Refused while a connect job
    runs: its settings write would reconnect right after the disconnect.
    """
    if request.args.get("confirm") != QUERY_FLAG_TRUE:
        return json_error(
            "Use ?confirm=true to confirm disconnecting and deleting the local clone",
            HTTPStatus.BAD_REQUEST, CODE_CONFIRMATION_REQUIRED,
        )
    if is_connect_running():
        return json_error(MESSAGE_CONNECT_IN_PROGRESS, HTTPStatus.CONFLICT, CODE_CONNECT_IN_PROGRESS)
    # Ordering + locking business rule lives in
    # services/shared_repo.disconnect_shared_repo.
    disconnect_shared_repo(log=SHARED_LOG)
    return jsonify({"configured": False})


def _shared_refresh(refresh_clone: Callable[[str], tuple[bool, str | None]]) -> Response | tuple[Response, int]:
    settings = read_settings()
    if not settings.url:
        return no_shared_repo_error(HTTPStatus.BAD_REQUEST)
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
            HTTPStatus.BAD_GATEWAY,
        )
    return jsonify({"stale": False, "lastSynced": last_synced_at(settings.url)})


def _shared_publish_start(project: str, start_publish: Callable[..., str]) -> tuple[Response, int]:
    err = path_segment_error(project)
    if err is not None:
        return json_error(err, HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
    settings = read_settings()
    if not settings.url:
        return no_shared_repo_error(HTTPStatus.BAD_REQUEST)
    access = resolve_access(settings.url)
    if not access.reachable:
        return access_failure_response(access)
    outcome = start_publish(project, settings.url, evaluations_root=Path(reports_dir()), env=access.env)
    if outcome == PublishStartResult.ALREADY_RUNNING:
        return json_error("a publish is already running", HTTPStatus.CONFLICT, "PUBLISH_IN_PROGRESS")
    if outcome != PublishStartResult.STARTED:
        return json_error(
            "could not start the publish job, see server logs",
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "PUBLISH_START_FAILED",
        )
    return jsonify({"started": True}), HTTPStatus.ACCEPTED


def register_shared_config_routes(app: Flask) -> None:
    """Bind the shared-repo status, config, refresh and publish routes."""
    app.get("/api/shared/status")(shared_status)
    app.put("/api/shared/config")(shared_config_put)
    app.delete("/api/shared/config")(shared_config_delete)

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        return _shared_refresh(refresh_shared_clone)

    @app.post("/api/projects/<project>/publish")
    def shared_publish_start(project: str) -> tuple[Response, int]:
        return _shared_publish_start(project, start_publish)
