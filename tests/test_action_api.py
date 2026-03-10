from __future__ import annotations

import os

import pytest

from quodeq.action_api import create_app
from quodeq.provider.base import ActionProvider, EvaluationOptions


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable auth for API tests that are not testing authentication."""
    monkeypatch.setenv("QUODEQ_AUTH_DISABLED", "1")


class StubProvider(ActionProvider):
    def list_projects(self, reports_dir: str):
        return {"projects": [{"name": "demo", "runsCount": 1, "latestRunId": "20260101", "latestDate": "2026-01-01"}]}

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

    def browse_repo(self, path: str | None):
        return {"current": "/tmp", "parent": "/", "directories": [], "isGitRepo": False}


def test_list_projects_endpoint():
    app = create_app(StubProvider())
    client = app.test_client()

    response = client.get("/api/projects")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["projects"][0]["name"] == "demo"


def test_start_evaluation_requires_repo():
    app = create_app(StubProvider())
    client = app.test_client()

    response = client.post("/api/evaluations", json={})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["code"] == "INVALID_INPUT"
