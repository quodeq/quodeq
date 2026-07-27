"""GET /api/evaluations/<id>/progress resolves the run budget from the snapshot.

The route used to read `snapshot.options`, a field JobSnapshot never had, so
`time_limit_s` was always None and the per-dim budget bar never rendered.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.core.types import JobSnapshot
from quodeq.services.base import ActionProvider


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture()
def reports_root(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", tmp)
        yield Path(tmp)


def _make_provider(run_dir: Path, time_limit_s):
    class _Provider(ActionProvider):
        def list_projects(self, reports_dir):
            return {"projects": []}

        def get_project_info(self, reports_dir, project):
            return {"project": project}

        def get_dashboard(self, reports_dir, project, run):
            return {}

        def get_accumulated(self, reports_dir, project, as_of):
            return {"summary": {"dimensionCount": 0}}

        def get_dimension_eval(self, reports_dir, project, run_id, dimension):
            return {}

        def get_run_plan(self, reports_dir, project, run_id):
            return {}

        def get_violations(self, reports_dir, project, run_id):
            return {"total": 0, "critical": 0, "major": 0, "minor": 0, "files": []}

        def start_evaluation(self, repo, reports_dir, options):
            return {"jobId": "job-1", "status": "running", "logs": []}

        def get_evaluation_status(self, job_id, reports_dir=None):
            if job_id != "job-1":
                return None
            return JobSnapshot(
                job_id="job-1", status="running", logs=[],
                output_project="proj", output_run_id="run-1",
                time_limit_s=time_limit_s,
            )

        def get_log_run_dir(self, job_id):
            return run_dir if job_id == "job-1" else None

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

    return _Provider()


def _write_running_run(reports_root: Path) -> Path:
    run_dir = reports_root / "proj" / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": "job-1",
            "state": "running",
            "started_at": "2026-04-26T12:00:00+00:00",
            "dimensions": ["security"],
            "phase": "analyzing",
        }),
        encoding="utf-8",
    )
    (run_dir / "evidence" / "security_queue.json").write_text(
        json.dumps({"taken": [], "pending": ["a.py"]}), encoding="utf-8",
    )
    return run_dir


def test_budget_resolved_from_snapshot(reports_root: Path):
    run_dir = _write_running_run(reports_root)
    client = create_app(_make_provider(run_dir, 600)).test_client()
    response = client.get("/api/evaluations/job-1/progress")
    assert response.status_code == 200
    dims = response.get_json()["dimensions"]
    assert dims[0]["budgetS"] == 600


def test_unlimited_budget_stays_absent(reports_root: Path):
    run_dir = _write_running_run(reports_root)
    client = create_app(_make_provider(run_dir, 0)).test_client()
    response = client.get("/api/evaluations/job-1/progress")
    assert response.status_code == 200
    dims = response.get_json()["dimensions"]
    assert dims[0].get("budgetS") is None
