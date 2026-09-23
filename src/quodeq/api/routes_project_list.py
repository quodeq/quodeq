"""Project listing, mutation, and export routes."""
from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import _path_from_body, error_response, json_error, page_params
from quodeq.shared.serialization import to_camel_dict
from quodeq.api.import_project import import_project as _import_project
from quodeq.api.routes_common import reports_dir
from quodeq.api.routes_project_create import _create_project
from quodeq.api.routes_project_scan import register_project_scan_routes
from quodeq.api.zip import export_project_zip
from quodeq.services.warmup import WarmupEngine, engine as warmup_engine
from quodeq.services.wiring import is_valid_repo_url
from quodeq.services.base import ActionProvider
from quodeq.shared.utils import is_repo_url
from quodeq.shared.validation import validate_canonical_absolute, validate_path_segment

_logger = logging.getLogger(__name__)


def _handle_delete_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle DELETE /api/projects/<project>."""
    project = request.view_args["project"]
    if request.args.get("confirm") != "true":
        return json_error("Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED")
    _logger.info("delete_project: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.delete_project(reports_dir(), project)
    if not ok:
        return json_error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
    return jsonify({"deleted": project})


def _validated_target_path(new_path: str) -> str | tuple[dict[str, Any], int]:
    """Return what the provider should store for *new_path*, or an error tuple.

    A value that looks like a repository URL is checked with
    ``is_valid_repo_url`` -- the same check the provider applies -- and
    passed through unchanged: relocating an online project to a new URL is
    supported here and is what the UI's "Enter the URL to restore" flow
    sends. Anything else must be an existing, canonical, absolute
    directory, and comes back resolved.
    """
    try:
        looks_like_url = is_repo_url(new_path)
    except ValueError:
        # Fixed message, not str(exc): is_repo_url only raises for cleartext
        # http://, always with the same reason -- never echo exception text.
        return error_response(
            "path must use https:// or git@; cleartext http:// repository URLs are rejected",
            HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
    if looks_like_url:
        if not is_valid_repo_url(new_path):
            return error_response(
                f"path must be a repository URL of the form https://host/owner/repo "
                f"or git@host:owner/repo.git, got {new_path!r}",
                HTTPStatus.BAD_REQUEST, "INVALID_URL",
            )
        return new_path

    try:
        resolved = validate_canonical_absolute(new_path)
    except (OSError, ValueError):
        # Fixed message, not str(exc): never echo exception text.
        return error_response(
            f"path must be an absolute, traversal-free directory, got {new_path!r}",
            HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
    if not resolved.is_dir():
        return error_response(
            f"path must be an existing directory, got {new_path!r}",
            HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
    return str(resolved)


def _handle_update_project_path(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle PATCH /api/projects/<project>/path.

    ``provider.update_project_path`` only ever returns a bare bool, so
    everything checkable up front (a malformed repository URL, a
    path-traversal attempt, a non-existent target) is validated by
    ``_validated_target_path`` and given its own message/code. Once that
    passes, a False from the provider can only mean the project itself is
    not registered, so NOT_FOUND is reserved for that case.
    """
    project = request.view_args["project"]
    data = request.get_json(silent=True) or {}
    raw_path = _path_from_body(data)
    if isinstance(raw_path, tuple):
        body, status = raw_path
        return jsonify(body), status
    if not raw_path:
        return json_error("Path is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
    new_path = _validated_target_path(raw_path)
    if isinstance(new_path, tuple):
        body, status = new_path
        return jsonify(body), status

    _logger.info("update_project_path: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.update_project_path(reports_dir(), project, new_path)
    if not ok:
        return json_error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
    return jsonify({"updated": project, "path": new_path})


def _invalid_project_name(project: str) -> tuple[Response, int] | None:
    """The 400 every per-project route returns for a malformed name, else None."""
    try:
        validate_path_segment(project)
    except ValueError:
        body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    return None


def _list_projects(
    provider: ActionProvider, warmup: WarmupEngine,
) -> Response | tuple[dict[str, Any], int]:
    """Return all projects with optional ``?limit=N&offset=M`` pagination.

    Pagination is pushed into the provider (``offset``/``limit``) so a
    paginated request only pays for hydrating its own window instead of
    the whole project set (see ``ProjectsCache._list_page``). ``limit=0``
    is this route's "no limit" sentinel, so 0 stays valid; anything
    malformed or negative answers 400 (see ``page_params``).
    """
    paging = page_params(request.args, default_limit=0, min_limit=0)
    if isinstance(paging[0], dict):
        return paging
    limit, offset = paging
    result = provider.list_projects(reports_dir(), offset=offset, limit=limit)
    projects = result.get("projects", [])
    # Self-healing warm-up: anything still pending on the page being
    # returned goes (back) on the queue, bounding this to page size
    # instead of the full project count.
    for entry in projects:
        if getattr(entry, "summary_pending", False):
            warmup.enqueue(entry.id)
    # Serialize at the boundary: providers hand back ProjectEntry
    # entities (or already-serialized dicts from remote providers).
    wire = [p if isinstance(p, dict) else to_camel_dict(p) for p in projects]
    payload = {**result, "projects": wire}
    snapshot = warmup.snapshot()
    if snapshot is not None:
        payload["warmup"] = snapshot
    return jsonify(payload)


def _project_info(provider: ActionProvider, project: str) -> Response | tuple[Response, int]:
    """Return repository metadata for a project."""
    invalid = _invalid_project_name(project)
    if invalid is not None:
        return invalid
    info = provider.get_project_info(reports_dir(), project)
    if not info:
        body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify(info)


def register_project_list_routes(
    app: Flask, provider: ActionProvider, warmup_engine: WarmupEngine = warmup_engine
) -> None:
    """Register project listing, mutation, and export routes."""
    register_project_scan_routes(app)

    @app.get("/api/projects")
    def list_projects() -> Response | tuple[dict[str, Any], int]:
        return _list_projects(provider, warmup_engine)

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        """Update the local filesystem path for a project."""
        return _invalid_project_name(project) or _handle_update_project_path(provider)

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        """Export a project as a ZIP archive."""
        return _invalid_project_name(project) or export_project_zip(project, reports_dir())

    @app.post("/api/projects/import")
    def import_project_route() -> Response | tuple[Response, int]:
        """Import a previously-exported project ZIP archive.

        Body: ``multipart/form-data`` with a ``file`` field containing the zip
        and an optional ``action`` field (``replace`` or ``copy``) used to
        resolve a 409 collision returned from a prior call.
        """
        return _import_project(reports_dir())

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        """Delete a project and all its run data."""
        return _invalid_project_name(project) or _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        return _project_info(provider, project)

    @app.post("/api/projects")
    def create_project() -> Response | tuple[Response, int]:
        """Register a new project (clone + scan) without starting an evaluation."""
        return _create_project(provider)
