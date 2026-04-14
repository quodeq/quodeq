"""Project listing, mutation, and export routes."""
from __future__ import annotations

import dataclasses
import json
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.api.zip import export_project_zip
from quodeq.services._fs_scan import scan_project
from quodeq.services.base import ActionProvider
from quodeq.shared.validation import validate_path_segment

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
    if ".." in new_path or not Path(new_path).is_absolute():
        body, status = error_response("Invalid path", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
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

    @app.get("/api/projects/<project>/scan")
    def project_scan(project: str) -> Response | tuple[Response, int]:
        """Return scan data for a project. Triggers scan if needed for local projects."""
        validate_path_segment(project)

        project_dir = Path(reports_dir()) / project
        if not project_dir.is_dir():
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        scan_path = project_dir / "scan.json"
        if scan_path.exists():
            try:
                data = json.loads(scan_path.read_text())
                return jsonify(data)
            except (json.JSONDecodeError, OSError):
                pass

        # Check if local — read repository_info.json
        info_path = project_dir / "repository_info.json"
        if not info_path.exists():
            body, status = error_response("No scan available", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status

        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            body, status = error_response("Could not read project info", HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL")
            return jsonify(body), status

        if info.get("location") != "local" or not info.get("path"):
            body, status = error_response("Scan only available for local projects", HTTPStatus.BAD_REQUEST, "NOT_LOCAL")
            return jsonify(body), status

        project_path = Path(info["path"])
        if not project_path.is_dir():
            body, status = error_response("Project path not found on disk", HTTPStatus.NOT_FOUND, "PATH_MISSING")
            return jsonify(body), status

        result = scan_project(project_path, output_dir=project_dir)
        return jsonify(dataclasses.asdict(result))

    @app.post("/api/scan")
    def scan_path() -> Response | tuple[Response, int]:
        """Scan a local path directly (no project required)."""
        data = request.get_json(silent=True) or {}
        target = data.get("path", "").strip()
        if not target:
            body, status = error_response("path is required", HTTPStatus.BAD_REQUEST, "MISSING_PATH")
            return jsonify(body), status

        target_path = Path(target).resolve()
        # Block scanning system directories to prevent information disclosure
        _blocked = ("/proc", "/sys", "/dev", "/etc", "/var/run", "/private/etc", "/private/var/run")
        if any(str(target_path).startswith(b) for b in _blocked):
            body, status = error_response("Cannot scan system directories", HTTPStatus.FORBIDDEN, "FORBIDDEN")
            return jsonify(body), status
        if not target_path.is_dir():
            body, status = error_response("Path is not a directory", HTTPStatus.BAD_REQUEST, "NOT_DIR")
            return jsonify(body), status

        result = scan_project(target_path)
        return jsonify(dataclasses.asdict(result))
