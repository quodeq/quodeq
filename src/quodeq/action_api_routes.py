"""Route registration helpers for the action API."""
from __future__ import annotations

import logging
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory

from quodeq.action_api_zip import export_project_zip
from quodeq.provider.base import ActionProvider
from quodeq.provider.tooling_mixin import _ALLOWED_CLIENT_IDS as _ALLOWED_AI_CMDS
from quodeq.shared.utils import get_evaluations_dir

_CREDENTIALS_RE = re.compile(r"(https?://)([^@]+)@")
_logger = logging.getLogger(__name__)


def _sanitize_url(url: str) -> str:
    """Remove embedded credentials from a URL for safe logging."""
    return _CREDENTIALS_RE.sub(r"\1***@", url)


def _error(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    return {"error": message, "code": code}, status


def _reports_dir() -> str:
    raw = request.args.get("evaluations") or get_evaluations_dir()
    resolved = Path(raw).resolve()
    default_resolved = Path(get_evaluations_dir()).resolve()
    if not resolved.is_relative_to(default_resolved) and not resolved.is_relative_to(Path.home()):
        from flask import abort
        abort(HTTPStatus.FORBIDDEN)
    return str(resolved)


def register_project_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project listing, mutation, and export routes."""

    @app.get("/api/projects")
    def list_projects() -> Response:
        """Return all projects in the reports directory."""
        return jsonify(provider.list_projects(_reports_dir()))

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str) -> Response | tuple[Response, int]:
        """Update the local filesystem path for a project."""
        data = request.get_json(silent=True) or {}
        new_path = data.get("path", "").strip()
        if not new_path:
            body, status = _error("Path is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        _logger.info("update_project_path: project=%s, remote_addr=%s", project, request.remote_addr)
        ok = provider.update_project_path(_reports_dir(), project, new_path)
        if not ok:
            body, status = _error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"updated": project, "path": new_path})

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        """Download a project's report directory as a zip archive."""
        return export_project_zip(project, _reports_dir())

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        """Delete a project and all its report data."""
        _logger.info("delete_project: project=%s, remote_addr=%s", project, request.remote_addr)
        ok = provider.delete_project(_reports_dir(), project)
        if not ok:
            body, status = _error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"deleted": project})

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        """Return metadata and available dimensions for a project."""
        info = provider.get_project_info(_reports_dir(), project)
        if not info:
            body, status = _error("Project info not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)


def register_project_data_routes(app: Flask, provider: ActionProvider) -> None:
    """Register project dashboard, accumulated, evaluation, and violation routes."""

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str) -> Response | tuple[Response, int]:
        """Return the dashboard payload for a project run."""
        run = request.args.get("run", "latest")
        try:
            payload = provider.get_dashboard(_reports_dir(), project, run)
        except FileNotFoundError:
            body, status = _error("Dashboard data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str) -> Response | tuple[Response, int]:
        """Return accumulated dimension scores across all runs."""
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(_reports_dir(), project, as_of)
        if payload is None:
            body, status = _error("Project not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
        """Return evaluation details for a single dimension in a run."""
        payload = provider.get_dimension_eval(_reports_dir(), project, run_id, dimension)
        if payload is None:
            body, status = _error("Eval file not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        if payload.get("waiting"):
            return jsonify(payload), HTTPStatus.ACCEPTED
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str) -> Response | tuple[Response, int]:
        """Return aggregated violation summary for a run."""
        try:
            payload = provider.get_violations(_reports_dir(), project, run_id)
        except FileNotFoundError:
            body, status = _error("Violation data not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)


def register_evaluation_list_routes(app: Flask, provider: ActionProvider) -> None:
    """Register evaluation listing and creation routes."""

    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        """Return all evaluation jobs."""
        return jsonify(provider.list_evaluations())

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        """Start a new evaluation job for a repository."""
        payload = request.get_json(silent=True) or {}
        repo = payload.get("repo")
        if not repo:
            body, status = _error("Repository is required", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        ai_cmd = payload.get("aiCmd") or None
        if ai_cmd and ai_cmd not in _ALLOWED_AI_CMDS:
            body, status = _error("Invalid AI command", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
        try:
            from quodeq.provider.base import EvaluationOptions
            job = provider.start_evaluation(
                repo=repo,
                reports_dir=_reports_dir(),
                options=EvaluationOptions(
                    discipline=payload.get("discipline"),
                    dimensions=payload.get("dimensions") or "",
                    numerical=bool(payload.get("numerical")),
                    ai_cmd=ai_cmd,
                    ai_model=payload.get("aiModel") or None,
                    subagent_model=payload.get("subagentModel") or None,
                ),
            )
        except (FileNotFoundError, ValueError):
            body, status = _error("Invalid repository", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(job), HTTPStatus.ACCEPTED


def register_evaluation_item_routes(app: Flask, provider: ActionProvider) -> None:
    """Register single-evaluation status and cancel routes."""

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """Return current status of an evaluation job."""
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = _error("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(job)

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """Cancel a running evaluation job."""
        _logger.info("cancel_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.cancel_evaluation(job_id)
        if not ok:
            body, status = _error("Job not found or not running", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})


def register_discovery_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/ai-clients/*, /api/plugins, /api/browse routes."""

    @app.get("/api/ai-clients")
    def ai_clients() -> Response:
        """Return available AI CLI clients."""
        return jsonify(provider.get_ai_clients())

    @app.get("/api/ai-clients/<client_id>/models")
    def client_models(client_id: str) -> Response:
        """Return available models for a specific AI client."""
        return jsonify(provider.get_client_models(client_id))

    @app.get("/api/plugins")
    def plugins() -> Response:
        """Return installed evaluator plugins with their dimensions."""
        from quodeq.provider.plugin_discovery import discover_plugins
        return jsonify(discover_plugins())

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        """List directories at a given path for repository browsing."""
        path = request.args.get("path")
        if path:
            resolved = Path(path).resolve()
            if not resolved.is_relative_to(Path.home()):
                body, status = _error("Path must be within user home directory", HTTPStatus.FORBIDDEN, "FORBIDDEN")
                return jsonify(body), status
        payload = provider.browse_repo(path)
        if "error" in payload:
            browse_status = HTTPStatus.BAD_REQUEST if "directory" in payload["error"].lower() else HTTPStatus.NOT_FOUND
            body, status = _error(payload["error"], browse_status, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(payload)


def register_static_routes(app: Flask, static_dist: str | None) -> None:
    """Register static file serving routes."""
    if not static_dist:
        return
    dist = Path(static_dist).resolve()
    if not dist.is_dir():
        return

    @app.route('/')
    def serve_root() -> Response:
        """Serve the SPA index page."""
        return send_from_directory(str(dist), 'index.html')

    @app.route('/<path:path>')
    def serve_static_or_spa(path: str) -> Response | tuple[Response, int]:
        """Serve a static file or fall back to the SPA index."""
        if (dist / path).is_file():
            return send_from_directory(str(dist), path)
        if path.startswith('api/'):
            return jsonify({"error": "Not found"}), HTTPStatus.NOT_FOUND
        return send_from_directory(str(dist), 'index.html')
