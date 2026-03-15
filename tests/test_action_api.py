from __future__ import annotations

import pytest

from quodeq.action_api import create_app
from quodeq.provider.base import ActionProvider, EvaluationOptions


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable auth by ensuring QUODEQ_API_KEY is unset so _check_auth() is a no-op."""
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


class StubProvider(ActionProvider):
    def list_projects(self, reports_dir: str):
        return {"projects": [{"name": "demo", "runsCount": 1, "latestRunId": "20260101", "latestDate": "2026-01-01"}]}

    def get_project_info(self, reports_dir: str, project: str):
        return {"project": project, "discipline": "python"}

    def get_dashboard(self, reports_dir: str, project: str, run: str):
        return {"project": project, "selectedRun": {"runId": run}}

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None):
        return {"project": project, "summary": {"dimensionCount": 0}}

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str):
        return {"dimension": dimension, "runId": run_id, "project": project, "principleGrades": []}

    def get_run_plan(self, reports_dir: str, project: str, run_id: str):
        return {"runId": run_id, "violations": []}

    def get_violations(self, reports_dir: str, project: str, run_id: str):
        return {"total": 0, "critical": 0, "major": 0, "minor": 0, "files": []}

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> dict:
        return {"jobId": "job-1", "status": "running", "logs": []}

    def get_evaluation_status(self, job_id: str):
        if job_id == "job-1":
            return {"jobId": "job-1", "status": "done", "logs": []}
        return None

    def cancel_evaluation(self, job_id: str) -> bool:
        return False

    def list_evaluations(self) -> list[dict]:
        return []

    def delete_project(self, reports_dir: str, project: str) -> bool:
        return project == "demo"

    def browse_repo(self, path: str | None):
        return {"current": "/tmp", "parent": "/", "directories": [], "isGitRepo": False}

    def get_ai_clients(self):
        return {"clients": []}

    def get_client_models(self, client_id: str):
        return {"models": []}


@pytest.fixture()
def client():
    """Flask test client backed by a StubProvider."""
    return create_app(StubProvider()).test_client()


def test_list_projects_endpoint(client):
    response = client.get("/api/projects")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["projects"][0]["name"] == "demo"


def test_start_evaluation_requires_repo(client):
    response = client.post("/api/evaluations", json={}, headers={"Origin": "http://localhost"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "INVALID_INPUT"


def test_dashboard_returns_project_data(client):
    response = client.get("/api/projects/demo/dashboard")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["project"] == "demo"


def test_delete_project_requires_confirm(client):
    response = client.delete("/api/projects/demo", headers={"Origin": "http://localhost"})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "CONFIRMATION_REQUIRED"


def test_delete_nonexistent_project_returns_404(client):
    response = client.delete(
        "/api/projects/nonexistent?confirm=true", headers={"Origin": "http://localhost"}
    )
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["code"] == "NOT_FOUND"


def test_get_evaluation_status_for_known_job(client):
    response = client.get("/api/evaluations/job-1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["jobId"] == "job-1"


def test_get_evaluation_status_unknown_returns_404(client):
    response = client.get("/api/evaluations/unknown-job")
    assert response.status_code == 404


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True


def test_plugins_endpoint(client):
    response = client.get("/api/plugins")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
