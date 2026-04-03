"""Project listing, mutation, and export routes."""
from __future__ import annotations

import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.api.zip import export_project_zip
from quodeq.services.base import ActionProvider

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
    _logger.info("update_project_path: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.update_project_path(reports_dir(), project, new_path)
    if not ok:
        body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    return jsonify({"updated": project, "path": new_path})


def _handle_clone_project_local(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle POST /api/projects/<project>/clone-local."""
    project = request.view_args["project"]
    data = request.get_json(silent=True) or {}
    destination = data.get("destination", "").strip()
    if not destination:
        body, status = error_response("destination is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    dest_resolved = Path(destination).resolve()
    home = Path.home().resolve()
    if not dest_resolved.is_relative_to(home):
        body, status = error_response(
            "Destination must be within the user's home directory",
            HTTPStatus.FORBIDDEN,
            "FORBIDDEN",
        )
        return jsonify(body), status
    if not dest_resolved.is_dir():
        body, status = error_response("Destination directory not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    _logger.info("clone_project_local: project=%s, dest=%s, remote_addr=%s", project, destination, request.remote_addr)
    result = provider.clone_to_local(reports_dir(), project, str(dest_resolved))
    if result is None:
        body, status = error_response("Clone failed — check project exists and is an online project", HTTPStatus.BAD_REQUEST, "CLONE_FAILED")
        return jsonify(body), status
    return jsonify(result)


def register_project_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project listing, mutation, and export routes."""

    @app.get("/api/projects")
    def list_projects() -> Response:
        """Return all projects with optional ``?limit=N&offset=M`` pagination."""
        result = provider.list_projects(reports_dir())
        projects = result.get("projects", [])
        offset = request.args.get("offset", 0, type=int)
        limit = request.args.get("limit", 0, type=int)
        if offset > 0:
            projects = projects[offset:]
        if limit > 0:
            projects = projects[:limit]
        return jsonify({**result, "projects": projects})

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        return _handle_update_project_path(provider)

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        return export_project_zip(project, reports_dir())

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        return _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        info = provider.get_project_info(reports_dir(), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.post("/api/projects/<project>/clone-local")
    def clone_project_local(project: str) -> Response | tuple[Response, int]:
        return _handle_clone_project_local(provider)
