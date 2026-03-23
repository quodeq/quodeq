"""Route registration helpers for the action API."""
from __future__ import annotations
import logging
import re
from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from quodeq.api.helpers import error_response, validate_evaluation_payload
from quodeq.api.zip import export_project_zip
from quodeq.core.types import to_camel_dict
from quodeq.provider.base import ActionProvider
from quodeq.provider.tooling_mixin import get_allowed_client_ids as _get_allowed_ai_cmds
from quodeq.shared.utils import get_evaluations_dir

_CREDENTIALS_RE = re.compile(r"(https?://)([^@]+)@")
_logger = logging.getLogger(__name__)

# Error keyword returned by browse_repo when the path exists but is not a directory.
_BROWSE_NOT_A_DIR_KEYWORD = "not a directory"


def _sanitize_url(url: str) -> str:
    """Remove embedded credentials from a URL for safe logging/error messages."""
    return _CREDENTIALS_RE.sub(r"\1***@", url)


def _reports_dir(default_path: str | None = None) -> str:
    """Resolve the reports directory from query params or *default_path*."""
    fallback = default_path if default_path is not None else get_evaluations_dir()
    raw = request.args.get("evaluations") or fallback
    resolved = Path(raw).resolve()
    default_resolved = Path(fallback).resolve()
    if not resolved.is_relative_to(default_resolved):
        from flask import abort
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


def _validate_ai_cmd(ai_cmd: str | None, env: dict[str, str] | None = None) -> tuple[Response, int] | None:
    """Return an error response if *ai_cmd* is not in the allow-list, or None if valid."""
    if not ai_cmd:
        return None
    allowed_cmds = _get_allowed_ai_cmds(env=env)
    if ai_cmd not in allowed_cmds:
        allowed_list = ", ".join(sorted(allowed_cmds))
        body, status = error_response(
            f"Invalid AI command. Allowed: {allowed_list}",
            HTTPStatus.BAD_REQUEST,
            "INVALID_INPUT",
        )
        return jsonify(body), status
    return None


def register_evaluation_list_routes(app: Flask, provider: ActionProvider, eval_rate_store: object | None = None) -> None:
    """Register evaluation listing and creation routes."""
    @app.get("/api/evaluations")
    def list_evaluations() -> Response:
        return jsonify([to_camel_dict(j) for j in provider.list_evaluations()])

    @app.post("/api/evaluations")
    def start_evaluation() -> Response | tuple[Response, int]:
        # Enforce stricter per-endpoint rate limit for evaluation creation
        if eval_rate_store is not None:
            import time as _time
            ip = request.remote_addr or "unknown"
            now = _time.monotonic()
            if eval_rate_store.check(ip, now):  # type: ignore[union-attr]
                body, status = error_response(
                    "Too many evaluation requests", HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED",
                )
                return jsonify(body), status
            eval_rate_store.record(ip, now)  # type: ignore[union-attr]
        payload = request.get_json(silent=True) or {}
        validation_error = validate_evaluation_payload(payload)
        if validation_error:
            body, status = error_response(validation_error, HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        repo = payload.get("repo")
        ai_cmd = payload.get("aiCmd") or None
        ai_cmd_error = _validate_ai_cmd(ai_cmd)
        if ai_cmd_error is not None:
            return ai_cmd_error
        _logger.info("start_evaluation: repo=%s, remote_addr=%s", _sanitize_url(repo), request.remote_addr)
        try:
            from quodeq.provider.base import EvaluationOptions
            max_subagents_raw = payload.get("maxSubagents", 5)
            max_subagents = max(1, min(10, int(max_subagents_raw)))
            pool_budget_raw = payload.get("poolBudget", 600)
            pool_budget = max(60, min(3600, int(pool_budget_raw)))
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
                    verify_findings=bool(payload.get("verifyFindings", False)),
                    max_subagents=max_subagents,
                    pool_budget=pool_budget,
                    incremental=bool(payload.get("incremental", False)),
                ),
            )
        except (FileNotFoundError, ValueError):
            body, status = error_response("Invalid repository", HTTPStatus.BAD_REQUEST, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(to_camel_dict(job)), HTTPStatus.ACCEPTED


def register_evaluation_item_routes(app: Flask, provider: ActionProvider) -> None:
    """Register single-evaluation status and cancel routes."""

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = error_response("Job not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(to_camel_dict(job))

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str) -> Response | tuple[Response, int]:
        _logger.info("cancel_evaluation: job_id=%s, remote_addr=%s", job_id, request.remote_addr)
        ok = provider.cancel_evaluation(job_id)
        if not ok:
            body, status = error_response("Job not found or not running", HTTPStatus.NOT_FOUND, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})


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
        from quodeq.provider.plugin_discovery import discover_plugins
        return jsonify([to_camel_dict(p) for p in discover_plugins()])

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
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
            return jsonify({"error": "Not found", "code": "NOT_FOUND"}), HTTPStatus.NOT_FOUND
        return send_from_directory(str(dist), 'index.html')
