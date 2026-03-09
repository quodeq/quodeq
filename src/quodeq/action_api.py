"""Flask REST API for project reports, evaluations, and tooling discovery."""

from __future__ import annotations

import os
from typing import Any

from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from quodeq.action_provider import ActionProvider
from quodeq.utils import ACTION_API_PORT

_DEFAULT_REPORTS_DIR = "evaluations"
_EVALUATIONS_DIR_ENV = "QUODEQ_EVALUATIONS_DIR"


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from quodeq.action_provider_fs import FilesystemActionProvider
    return FilesystemActionProvider()


def _error(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    return {"error": message, "code": code}, status


def _reports_dir() -> str:
    return request.args.get("evaluations") or os.environ.get(_EVALUATIONS_DIR_ENV, _DEFAULT_REPORTS_DIR)


def _build_project_zip(project_path: Path) -> "io.BytesIO":
    """Create an in-memory zip archive of a project directory."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_entry in project_path.rglob("*"):
            if file_entry.is_file():
                zf.write(file_entry, file_entry.relative_to(project_path.parent))
    buf.seek(0)
    return buf


def _register_project_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/projects/* routes."""

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
            body, status = _error("Path is required", 400, "INVALID_INPUT")
            return jsonify(body), status
        ok = provider.update_project_path(_reports_dir(), project, new_path)
        if not ok:
            body, status = _error("Project not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"updated": project, "path": new_path})

    @app.get("/api/projects/<project>/export")
    def export_project(project: str) -> Response | tuple[Response, int]:
        """Download a project's report directory as a zip archive."""
        from flask import send_file
        project_path = Path(_reports_dir()) / project
        if not project_path.exists() or not project_path.is_dir():
            body, status = _error("Project not found", 404, "NOT_FOUND")
            return jsonify(body), status
        buf = _build_project_zip(project_path)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{project}.zip")

    @app.delete("/api/projects/<project>")
    def delete_project(project: str) -> Response | tuple[Response, int]:
        """Delete a project and all its report data."""
        ok = provider.delete_project(_reports_dir(), project)
        if not ok:
            return jsonify({"error": "Project not found"}), 404
        return jsonify({"deleted": project})

    @app.get("/api/projects/<project>/info")
    def project_info(project: str) -> Response | tuple[Response, int]:
        """Return metadata and available dimensions for a project."""
        info = provider.get_project_info(_reports_dir(), project)
        if not info:
            body, status = _error("Project info not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str) -> Response | tuple[Response, int]:
        """Return the dashboard payload for a project run."""
        run = request.args.get("run", "latest")
        try:
            payload = provider.get_dashboard(_reports_dir(), project, run)
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str) -> Response | tuple[Response, int]:
        """Return accumulated dimension scores across all runs."""
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(_reports_dir(), project, as_of)
        if payload is None:
            body, status = _error("Project not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str) -> Response | tuple[Response, int]:
        """Return evaluation details for a single dimension in a run."""
        payload = provider.get_dimension_eval(_reports_dir(), project, run_id, dimension)
        if payload is None:
            body, status = _error("Eval file not found", 404, "NOT_FOUND")
            return jsonify(body), status
        if payload.get("waiting"):
            return jsonify(payload), 202
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str) -> Response | tuple[Response, int]:
        """Return aggregated violation summary for a run."""
        try:
            payload = provider.get_violations(_reports_dir(), project, run_id)
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)


def _register_evaluation_routes(app: Flask, provider: ActionProvider) -> None:
    """Register /api/evaluations/* routes."""

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
            body, status = _error("Repository is required", 400, "INVALID_INPUT")
            return jsonify(body), status
        try:
            from quodeq.action_provider import EvaluationOptions
            job = provider.start_evaluation(
                repo=repo,
                reports_dir=_reports_dir(),
                options=EvaluationOptions(
                    discipline=payload.get("discipline"),
                    dimensions=payload.get("dimensions") or "",
                    numerical=bool(payload.get("numerical")),
                    ai_cmd=payload.get("aiCmd") or None,
                    ai_model=payload.get("aiModel") or None,
                ),
            )
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 400, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(job), 202

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """Return current status of an evaluation job."""
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = _error("Job not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(job)

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str) -> Response | tuple[Response, int]:
        """Cancel a running evaluation job."""
        ok = provider.cancel_evaluation(job_id)
        if not ok:
            body, status = _error("Job not found or not running", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})


def _register_discovery_routes(app: Flask, provider: ActionProvider) -> None:
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
        import json as _json
        from quodeq.config.paths import default_paths
        evaluators_root = default_paths().evaluators_dir
        result: list[dict[str, Any]] = []
        if evaluators_root.is_dir():
            for child in sorted(evaluators_root.iterdir()):
                if not child.is_dir() or child.name.startswith("_"):
                    continue
                plugin_file = child / "plugin.json"
                dims_file = child / "dimensions.json"
                if not plugin_file.exists():
                    continue
                try:
                    plugin_data = _json.loads(plugin_file.read_text())
                    dims_data = _json.loads(dims_file.read_text()) if dims_file.exists() else {"applies": []}
                    result.append({
                        "id": plugin_data.get("id", child.name),
                        "name": plugin_data.get("name", child.name),
                        "extensions": plugin_data.get("detects", {}).get("extensions", []),
                        "dimensions": [
                            {"id": d["id"], "weight": d.get("weight", 1), "iso_25010": d.get("iso_25010")}
                            for d in dims_data.get("applies", [])
                        ],
                    })
                except (KeyError, ValueError):
                    continue
        return jsonify(result)

    @app.get("/api/browse")
    def browse() -> Response | tuple[Response, int]:
        """List directories at a given path for repository browsing."""
        path = request.args.get("path")
        payload = provider.browse_repo(path)
        if "error" in payload:
            body, status = _error(payload["error"], 400 if "directory" in payload["error"].lower() else 404, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(payload)


def _register_static_routes(app: Flask, static_dist: str | None) -> None:
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
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(str(dist), 'index.html')


def create_app(provider: ActionProvider | None = None, static_dist: str | None = None) -> Flask:
    """Create and configure the Flask application with all API routes."""
    app = Flask(__name__)
    provider = provider or _default_provider()

    @app.get("/api/health")
    def health() -> Response:
        """Return a simple health-check response."""
        return jsonify({"ok": True})

    _register_project_routes(app, provider)
    _register_evaluation_routes(app, provider)
    _register_discovery_routes(app, provider)
    _register_static_routes(app, static_dist)
    return app


def main() -> None:
    """Start the Flask development server using environment configuration."""
    port = int(os.environ.get("QUODEQ_ACTION_API_PORT", str(ACTION_API_PORT)))
    host = os.environ.get("QUODEQ_ACTION_API_HOST", "127.0.0.1")
    static_dist = os.environ.get("QUODEQ_STATIC_DIST")
    app = create_app(static_dist=static_dist)
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
