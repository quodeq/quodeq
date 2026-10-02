"""Config/status/lifecycle routes for the shared results repository.

Status, config PUT/DELETE, refresh, and the local project-publish route.
``start_refresh``, ``start_publish`` and ``start_connect`` are
imported directly from their real owner, never through the ``routes_shared``
facade, so this module never imports back a sibling that imports it. Tests
patch "quodeq.api.routes_shared_config.start_refresh" /
"...start_publish" / "...start_connect".
"""
from __future__ import annotations

from functools import partial
from http import HTTPStatus
from pathlib import Path
from typing import Callable

from flask import Flask, Response, jsonify, request

from quodeq.api._constants import CODE_INVALID_INPUT, QUERY_FLAG_TRUE
from quodeq.api.routes_github_access import same_url_access_error
from quodeq.services.base import ActionProvider
from quodeq.services.github_access import resolve_access
from quodeq.services.shared_connect_job import (
    ConnectStartResult,
    get_connect_status,
    is_connect_running,
    start_connect,
    url_failure,
)
from quodeq.services.shared_pull_job import get_pull_status, is_pull_running
from quodeq.services.shared_publish import PublishStartResult, get_publish_status, start_publish
from quodeq.services.shared_refresh_job import (
    RefreshStartResult,
    get_refresh_status,
    is_refresh_running,
    start_refresh,
)
from quodeq.services.shared_repo import disconnect_shared_repo, last_synced_at, read_state
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
CODE_REFRESH_IN_PROGRESS = "REFRESH_IN_PROGRESS"
CODE_REFRESH_START_FAILED = "REFRESH_START_FAILED"
INVITE_TEXT = "Open quodeq, choose Join your team's results, paste {url}"


def sync_block(snapshot: dict) -> dict:
    """camelCase one job slot for the wire."""
    out = dict(snapshot)
    out["finishedAt"] = out.pop("finished_at", None)
    out["projectsFound"] = out.pop("projects_found", None)
    if "project_id" in out:
        out["projectId"] = out.pop("project_id")
        out["projectName"] = out.pop("project_name", None)
    if "source_project_id" in out:
        out["sourceProjectId"] = out.pop("source_project_id")
        out["conflictKind"] = out.pop("conflict_kind", None)
    return out


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
    connect = sync_block(get_connect_status())
    refresh = sync_block(get_refresh_status())
    pull = sync_block(get_pull_status())
    return jsonify(
        {
            "configured": settings.url is not None,
            "url": settings.url,
            "lastSynced": synced,
            "syncing": is_connect_running() or is_refresh_running() or is_pull_running(),
            # Reserved for sync-level failures; always present so the UI
            # can bind to it without existence checks. A reserved slot is
            # not an error response, so it carries no "code" (the
            # error-code gate exempts an "error" value of None).
            "error": None,
            "publish": publish,
            "connect": connect,
            "refresh": refresh,
            "pull": pull,
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
    # The clone dir is keyed by the configured URL, so an ssh results-repo URL
    # reachable only through a token rung (https) is refused with the https form.
    access = resolve_access(url)
    error = same_url_access_error(url, access)
    if error is not None:
        return error
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


def shared_config_delete(provider: ActionProvider) -> Response | tuple[Response, int]:
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
    provider.invalidate_projects_cache()
    return jsonify({"configured": False})


def _shared_refresh_start(start: Callable[..., RefreshStartResult]) -> Response | tuple[Response, int]:
    settings = read_settings()
    if not settings.url:
        return no_shared_repo_error(HTTPStatus.BAD_REQUEST)
    access = resolve_access(settings.url)
    error = same_url_access_error(settings.url, access)
    if error is not None:
        return error
    outcome = start(settings.url, env=access.env, log=SHARED_LOG)
    if outcome == RefreshStartResult.ALREADY_RUNNING:
        return json_error("a refresh is already running", HTTPStatus.CONFLICT, CODE_REFRESH_IN_PROGRESS)
    if outcome != RefreshStartResult.STARTED:
        return json_error(
            "could not start the refresh job, see server logs",
            HTTPStatus.INTERNAL_SERVER_ERROR, CODE_REFRESH_START_FAILED,
        )
    return jsonify({"started": True}), HTTPStatus.ACCEPTED


def shared_invite() -> Response | tuple[Response, int]:
    """The sentence a teammate needs to join: where to click and what to paste."""
    settings = read_settings()
    if not settings.url:
        return no_shared_repo_error(HTTPStatus.BAD_REQUEST)
    return jsonify({"text": INVITE_TEXT.format(url=settings.url)})


def _shared_publish_start(project: str, start_publish: Callable[..., str]) -> tuple[Response, int]:
    err = path_segment_error(project)
    if err is not None:
        return json_error(err, HTTPStatus.BAD_REQUEST, CODE_INVALID_INPUT)
    settings = read_settings()
    if not settings.url:
        return no_shared_repo_error(HTTPStatus.BAD_REQUEST)
    access = resolve_access(settings.url)
    error = same_url_access_error(settings.url, access)
    if error is not None:
        return error
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


def register_shared_config_routes(app: Flask, provider: ActionProvider) -> None:
    """Bind the shared-repo status, config, refresh and publish routes."""
    app.get("/api/shared/status")(shared_status)
    app.put("/api/shared/config")(shared_config_put)
    app.delete("/api/shared/config", endpoint="shared_config_delete")(partial(shared_config_delete, provider))

    app.get("/api/shared/invite")(shared_invite)

    @app.post("/api/shared/refresh")
    def shared_refresh() -> Response | tuple[Response, int]:
        return _shared_refresh_start(start_refresh)

    @app.post("/api/projects/<project>/publish")
    def shared_publish_start(project: str) -> tuple[Response, int]:
        return _shared_publish_start(project, start_publish)
