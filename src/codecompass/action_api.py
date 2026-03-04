from __future__ import annotations

import os
from typing import Any

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from codecompass.action_provider import ActionProvider


def _default_provider() -> ActionProvider:
    """Create the default filesystem-based provider (lazy import)."""
    from codecompass.action_provider_fs import FilesystemActionProvider
    return FilesystemActionProvider()


def _error(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    return {"error": message, "code": code}, status


def _reports_dir() -> str:
    return request.args.get("evaluations") or os.environ.get("CODECOMPASS_EVALUATIONS_DIR", "evaluations")


def create_app(provider: ActionProvider | None = None, static_dist: str | None = None) -> Flask:
    app = Flask(__name__)
    provider = provider or _default_provider()

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/projects")
    def list_projects():
        return jsonify(provider.list_projects(_reports_dir()))

    @app.patch("/api/projects/<project>/path")
    def update_project_path(project: str):
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
    def export_project(project: str):
        import io
        import zipfile
        from pathlib import Path as _Path
        from flask import send_file
        project_path = _Path(_reports_dir()) / project
        if not project_path.exists() or not project_path.is_dir():
            body, status = _error("Project not found", 404, "NOT_FOUND")
            return jsonify(body), status
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in project_path.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(project_path.parent))
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{project}.zip")

    @app.delete("/api/projects/<project>")
    def delete_project(project: str):
        ok = provider.delete_project(_reports_dir(), project)
        if not ok:
            return jsonify({"error": "Project not found"}), 404
        return jsonify({"deleted": project})

    @app.get("/api/projects/<project>/info")
    def project_info(project: str):
        info = provider.get_project_info(_reports_dir(), project)
        if not info:
            body, status = _error("Project info not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(info)

    @app.get("/api/projects/<project>/dashboard")
    def dashboard(project: str):
        run = request.args.get("run", "latest")
        try:
            payload = provider.get_dashboard(_reports_dir(), project, run)
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/accumulated")
    def accumulated(project: str):
        as_of = request.args.get("asOf")
        payload = provider.get_accumulated(_reports_dir(), project, as_of)
        if payload is None:
            body, status = _error("Project not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval")
    def dimension_eval(project: str, run_id: str, dimension: str):
        payload = provider.get_dimension_eval(_reports_dir(), project, run_id, dimension)
        if payload is None:
            body, status = _error("Eval file not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/projects/<project>/runs/<run_id>/violations")
    def run_violations(project: str, run_id: str):
        try:
            payload = provider.get_violations(_reports_dir(), project, run_id)
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(payload)

    @app.get("/api/evaluations")
    def list_evaluations():
        return jsonify(provider.list_evaluations())

    @app.post("/api/evaluations")
    def start_evaluation():
        payload = request.get_json(silent=True) or {}
        repo = payload.get("repo")
        if not repo:
            body, status = _error("Repository is required", 400, "INVALID_INPUT")
            return jsonify(body), status
        try:
            job = provider.start_evaluation(
                repo=repo,
                discipline=payload.get("discipline"),
                dimensions=payload.get("dimensions") or "",
                numerical=bool(payload.get("numerical")),
                reports_dir=_reports_dir(),
                ai_cmd=payload.get("aiCmd") or None,
                ai_model=payload.get("aiModel") or None,
            )
        except FileNotFoundError as exc:
            body, status = _error(str(exc), 400, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(job), 202

    @app.get("/api/evaluations/<job_id>")
    def get_evaluation(job_id: str):
        job = provider.get_evaluation_status(job_id)
        if not job:
            body, status = _error("Job not found", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify(job)

    @app.delete("/api/evaluations/<job_id>")
    def cancel_evaluation(job_id: str):
        ok = provider.cancel_evaluation(job_id)
        if not ok:
            body, status = _error("Job not found or not running", 404, "NOT_FOUND")
            return jsonify(body), status
        return jsonify({"ok": True})

    @app.get("/api/ai-clients")
    def ai_clients():
        return jsonify(provider.get_ai_clients())

    @app.get("/api/ai-clients/<client_id>/models")
    def client_models(client_id: str):
        return jsonify(provider.get_client_models(client_id))

    @app.get("/api/browse")
    def browse():
        path = request.args.get("path")
        payload = provider.browse_repo(path)
        if "error" in payload:
            body, status = _error(payload["error"], 400 if "directory" in payload["error"].lower() else 404, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(payload)

    if static_dist:
        dist = Path(static_dist).resolve()
        if dist.is_dir():
            @app.route('/')
            def serve_root():
                return send_from_directory(str(dist), 'index.html')

            @app.route('/<path:path>')
            def serve_static_or_spa(path):
                if (dist / path).is_file():
                    return send_from_directory(str(dist), path)
                if path.startswith('api/'):
                    return jsonify({"error": "Not found"}), 404
                return send_from_directory(str(dist), 'index.html')

    return app


def main() -> None:
    port = int(os.environ.get("CODECOMPASS_ACTION_API_PORT", "8001"))
    host = os.environ.get("CODECOMPASS_ACTION_API_HOST", "127.0.0.1")
    static_dist = os.environ.get("CODECOMPASS_STATIC_DIST")
    app = create_app(static_dist=static_dist)
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
