"""GET /api/evaluations/<id> surfaces the per-dim state map."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider, EvaluationOptions
from quodeq.services._job_model import JobSnapshot
from quodeq.shared.dimensions_state import DimState, write_dim_state


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture()
def reports_root(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", tmp)
        yield Path(tmp)


class _Provider(ActionProvider):
    """Minimal provider exposing one running job tied to a real run dir."""

    def list_projects(self, reports_dir: str):
        return {"projects": []}

    def get_project_info(self, reports_dir: str, project: str):
        return {"project": project}

    def get_dashboard(self, reports_dir: str, project: str, run: str):
        return {}

    def get_accumulated(self, reports_dir: str, project: str, as_of):
        return {"summary": {"dimensionCount": 0}}

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str):
        return {}

    def get_run_plan(self, reports_dir: str, project: str, run_id: str):
        return {}

    def get_violations(self, reports_dir: str, project: str, run_id: str):
        return {"total": 0, "critical": 0, "major": 0, "minor": 0, "files": []}

    def start_evaluation(self, repo, reports_dir, options):
        return {"jobId": "job-1", "status": "running", "logs": []}

    def get_evaluation_status(self, job_id, reports_dir=None):
        if job_id != "job-1":
            return None
        return JobSnapshot(
            job_id="job-1", status="running", logs=[],
            output_project="proj", output_run_id="run-1",
        )

    def cancel_evaluation(self, job_id, reports_dir=None, *, discard_partial=False):
        return False

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return []

    def delete_project(self, reports_dir, project):
        return False

    def browse_repo(self, path=None):
        return {"current": "/", "parent": None, "directories": [], "isGitRepo": False}

    def get_ai_clients(self):
        return {"clients": []}

    def get_client_models(self, client_id):
        return {"models": []}


@pytest.fixture()
def client():
    return create_app(_Provider()).test_client()


def test_dim_states_present_in_response(client, reports_root: Path):
    run_dir = reports_root / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    write_dim_state(run_dir, "security", DimState.PENDING)
    write_dim_state(run_dir, "security", DimState.RUNNING)
    write_dim_state(run_dir, "security", DimState.DONE)
    write_dim_state(run_dir, "reliability", DimState.PENDING)
    write_dim_state(run_dir, "reliability", DimState.RUNNING)
    write_dim_state(run_dir, "reliability", DimState.INCOMPLETE, reason="cancelled_by_user")

    response = client.get("/api/evaluations/job-1")
    assert response.status_code == 200
    payload = response.get_json()
    states = payload["dimStates"]
    assert states["security"]["state"] == "done"
    assert states["reliability"]["state"] == "incomplete"
    assert states["reliability"]["reason"] == "cancelled_by_user"


def test_dim_states_empty_when_run_dir_missing(client):
    response = client.get("/api/evaluations/job-1")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["dimStates"] == {}
