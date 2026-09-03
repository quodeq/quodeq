"""Project listing, mutation, and export routes."""
from __future__ import annotations

import logging
from http import HTTPStatus

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.shared.serialization import to_camel_dict
from quodeq.api.import_project import import_project as _import_project
from quodeq.api.routes_common import reports_dir
from quodeq.api.routes_project_create import _create_project
from quodeq.api.routes_project_scan import register_project_scan_routes
from quodeq.api.zip import export_project_zip
from quodeq.services._warmup import engine as warmup_engine
from quodeq.services.base import ActionProvider
from quodeq.shared.validation import validate_canonical_absolute, validate_path_segment

_logger = logging.getLogger(__name__)


def _handle_delete_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle DELETE /api/projects/<project>."""
    project = request.view_args["project"]
    if request.args.get("confirm") != "true":
        body, status = error_response("Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED")
        return jsonify(body), status
    _logger.info("delete_project: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.delete_project(reports_dir(), project)
    if not ok:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify({"deleted": project})


def _handle_update_project_path(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle PATCH /api/projects/<project>/path."""
    project = request.view_args["project"]
    data = request.get_json(silent=True) or {}
    new_path = data.get("path", "").strip()
    if not new_path:
        body, status = error_response("Path is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    try:
        resolved = validate_canonical_absolute(new_path)
    except (OSError, ValueError):
        body, status = error_response("Invalid path", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    new_path = str(resolved)
    _logger.info("update_project_path: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.update_project_path(reports_dir(), project, new_path)
    if not ok:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify({"updated": project, "path": new_path})


def register_project_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project listing, mutation, and export routes."""
    register_project_scan_routes(app)

    @app.get("/api/projects")
    def list_projects() -> Response:
        """Return all projects with optional ``?limit=N&offset=M`` pagination."""
        result = provider.list_projects(reports_dir())
        projects = result.get("projects", [])
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 0, type=int)
        if offset > 0 or limit > 0:
            end = offset + limit if limit > 0 else None
            projects = projects[offset:end]
        # Self-healing warm-up: anything still pending on the page being
        # returned goes (back) on the queue, bounding this to page size
        # instead of the full project count.
        for entry in projects:
            if getattr(entry, "summary_pending", False):
                warmup_engine.enqueue(entry.id)
        # Serialize at the boundary: providers hand back ProjectEntry
        # entities (or already-serialized dicts from remote providers).
        wire = [p if isinstance(p, dict) else to_camel_dict(p) for p in projects]
        payload = {**result, "projects": wire}
        snapshot = warmup_engine.snapshot()
        if snapshot is not None:
            payload["warmup"] = snapshot
        return jsonify(payload)

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        """Update the local filesystem path for a project."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return _handle_update_project_path(provider)

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        """Export a project as a ZIP archive."""
        return export_project_zip(project, reports_dir())

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
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        """Return repository metadata for a project."""
        try:
            validate_path_segment(project)
        except ValueError:
            body, status = error_response("Invalid project name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        info = provider.get_project_info(reports_dir(), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.post("/api/projects")
    def create_project() -> Response | tuple[Response, int]:
        """Register a new project (clone + scan) without starting an evaluation."""
        return _create_project(provider)
