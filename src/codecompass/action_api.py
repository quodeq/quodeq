from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request

from codecompass.action_provider import ActionProvider
from codecompass.action_provider_fs import FilesystemActionProvider


def _error(message: str, status: int, code: str) -> tuple[dict[str, Any], int]:
    return {"error": message, "code": code}, status


def _reports_dir() -> str:
    return request.args.get("evaluations") or os.environ.get("CODECOMPASS_EVALUATIONS_DIR", "evaluations")


def create_app(provider: ActionProvider | None = None) -> Flask:
    app = Flask(__name__)
    provider = provider or FilesystemActionProvider()

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/projects")
    def list_projects():
        return jsonify(provider.list_projects(_reports_dir()))

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

    @app.get("/api/browse")
    def browse():
        path = request.args.get("path")
        payload = provider.browse_repo(path)
        if "error" in payload:
            body, status = _error(payload["error"], 400 if "directory" in payload["error"].lower() else 404, "INVALID_INPUT")
            return jsonify(body), status
        return jsonify(payload)

    return app


def main() -> None:
    port = int(os.environ.get("CODECOMPASS_ACTION_API_PORT", "8001"))
    host = os.environ.get("CODECOMPASS_ACTION_API_HOST", "127.0.0.1")
    app = create_app()
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
