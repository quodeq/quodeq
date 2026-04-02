"""Route registration helpers for the action API."""
from __future__ import annotations
import logging
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

from quodeq.api.helpers import error_response, register_static_routes
from quodeq.api.zip import export_project_zip
from quodeq.core.types import to_camel_dict
from quodeq.provider.base import ActionProvider
from quodeq.shared.utils import get_evaluations_dir

# Re-export evaluation routes so existing imports from this module keep working.
from quodeq.api.routes_evaluation import (  # noqa: F401
    register_evaluation_list_routes,
    register_evaluation_item_routes,
)

_logger = logging.getLogger(__name__)

# Error keyword returned by browse_repo when the path exists but is not a directory.
_BROWSE_NOT_A_DIR_KEYWORD = "not a directory"


def _reports_dir(default_path: str | None = None, request_args: dict | None = None) -> str:
    """Resolve the reports directory from query params or *default_path*.

    *request_args* overrides ``request.args`` when provided, allowing the
    function to be called without a live Flask request context (e.g. in tests).
    """
    fallback = default_path if default_path is not None else get_evaluations_dir()
    args = request_args if request_args is not None else request.args
    raw = args.get("evaluations") or fallback
    resolved = Path(raw).resolve()
    default_resolved = Path(fallback).resolve()
    if not resolved.is_relative_to(default_resolved):
        abort(HTTPStatus.FORBIDDEN)
    return str(resolved)


def _handle_delete_project(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle DELETE /api/projects/<project>."""
    project = request.view_args["project"]
    if request.args.get("confirm") != "true":
        body, status = error_response("Use ?confirm=true to confirm deletion", HTTPStatus.BAD_REQUEST, "CONFIRMATION_REQUIRED")
        return jsonify(body), status
    _logger.info("delete_project: project=%s, remote_addr=%s", project, request.remote_addr)
    ok = provider.delete_project(_reports_dir(), project)
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
    ok = provider.update_project_path(_reports_dir(), project, new_path)
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
    result = provider.clone_to_local(_reports_dir(), project, str(dest_resolved))
    if result is None:
        body, status = error_response("Clone failed — check project exists and is an online project", HTTPStatus.BAD_REQUEST, "CLONE_FAILED")
        return jsonify(body), status
    return jsonify(result)


def register_project_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project listing, mutation, and export routes."""

    @app.get("/api/projects")
    def list_projects() -> Response:
        """Return all projects with optional ``?limit=N&offset=M`` pagination."""
        result = provider.list_projects(_reports_dir())
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
        return export_project_zip(project, _reports_dir())

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        return _handle_delete_project(provider)

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        info = provider.get_project_info(_reports_dir(), project)
        if not info:
            body, status = error_response("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.post("/api/projects/<project>/clone-local")
    def clone_project_local(project: str) -> Response | tuple[Response, int]:
        return _handle_clone_project_local(provider)


def register_project_data_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project dashboard, accumulated, evaluation, and violation routes."""

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str) -> Response | tuple[Response, int]:
        run = request.args.get("run", "latest")
        try:
            payload = provider.get_dashboard(_reports_dir(), project, run)
        except FileNotFoundError:
            body, status = error_response("Dashboard data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str) -> Response | tuple[Response, int]:
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(_reports_dir(), project, as_of)
        if payload is None:
            body, status = error_response("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        # DEBUG: log reliability score from accumulated
        for d in (payload or {}).get("dimensions", []):
            if "reliab" in (d.get("dimension") or "").lower():
                _logger.warning("[DEBUG-ACC] asOf=%s reliability=%s viol=%s", as_of, d.get("overallScore"), d.get("totals", {}).get("violationCount"))
                break
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
        payload = provider.get_dimension_eval(_reports_dir(), project, run_id, dimension)
        if payload is None:
            body, status = error_response("Eval file not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        if payload.get("waiting"):
            return jsonify(payload), HTTPStatus.ACCEPTED
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str) -> Response | tuple[Response, int]:
        try:
            payload = provider.get_violations(_reports_dir(), project, run_id)
        except FileNotFoundError:
            body, status = error_response("Violation data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(payload))


def _handle_browse(provider: ActionProvider) -> Response | tuple[Response, int]:
    """Handle GET /api/browse."""
    path = request.args.get("path")
    if path:
        resolved = Path(path).resolve()
        home = Path.home().resolve()
        if not resolved.is_relative_to(home):
            body, status = error_response(
                "Path must be within the user's home directory",
                HTTPStatus.FORBIDDEN,
                "FORBIDDEN",
            )
            return jsonify(body), status
    payload = provider.browse_repo(path)
    if "error" in payload:
        raw_error = payload["error"]
        is_not_dir = _BROWSE_NOT_A_DIR_KEYWORD in raw_error.lower()
        browse_status = HTTPStatus.BAD_REQUEST if is_not_dir else HTTPStatus.NOT_FOUND
        safe_msg = "Path is not a directory" if is_not_dir else "Path not found or not accessible"
        body, status = error_response(safe_msg, browse_status, "INVALID_INPUT")
        return jsonify(body), status
    return jsonify(payload)


def _handle_browse_mkdir() -> Response | tuple[Response, int]:
    """Handle POST /api/browse/mkdir — create a new subdirectory."""
    data = request.get_json(silent=True) or {}
    parent = data.get("path", "").strip()
    name = data.get("name", "").strip()
    if not parent or not name:
        body, status = error_response("path and name are required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    if "/" in name or "\\" in name or name in (".", ".."):
        body, status = error_response("Invalid folder name", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
        return jsonify(body), status
    resolved = Path(parent).resolve()
    home = Path.home().resolve()
    if not resolved.is_relative_to(home):
        body, status = error_response(
            "Path must be within the user's home directory",
            HTTPStatus.FORBIDDEN,
            "FORBIDDEN",
        )
        return jsonify(body), status
    if not resolved.is_dir():
        body, status = error_response("Parent path not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        return jsonify(body), status
    target = resolved / name
    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        body, status = error_response("Folder already exists", HTTPStatus.CONFLICT, "CONFLICT")
        return jsonify(body), status
    except OSError as exc:
        body, status = error_response(f"Could not create folder: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR, "SERVER_ERROR")
        return jsonify(body), status
    return jsonify({"created": True, "path": str(target)})


def register_discovery_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/ai-clients/*, /api/plugins, /api/browse routes."""

    @app.get("/api/ai-clients")
    def ai_clients() -> Response:
        return jsonify(provider.get_ai_clients())

    @app.get("/api/ai-clients/<client_id>/models")
    def client_models(client_id: str) -> Response:
        return jsonify(provider.get_client_models(client_id))

    @app.get("/api/plugins")
    def plugins() -> Response:
        from quodeq.provider.plugin_discovery import discover_plugins  # deferred: avoid circular import at module level
        return jsonify([to_camel_dict(p) for p in discover_plugins()])

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        return _handle_browse(provider)

    @app.post("/api/browse/mkdir")
    def browse_mkdir() -> Response | tuple[Response, int]:
        return _handle_browse_mkdir()


__all__ = ["register_static_routes"]  # re-exported from quodeq.api.helpers
