"""Tests for GET /api/evaluations/active.

The endpoint is the single authoritative answer to "is an evaluation
actually running", replacing the copy of the staleness rule that the native
window shell (dashboard/_webview_window) used to run by cross-referencing
/api/evaluations and /api/projects itself. The rule under test here is the
one that moved: a running job whose outputProject is no longer in the
project list is stale; jobs without an outputProject stay valid; a failing
project lookup falls back to the first running job.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from quodeq.core.types import JobSnapshot, ProjectEntry
from quodeq.services.base import ActionProvider


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable auth by ensuring QUODEQ_API_KEY is unset so _check_auth() is a no-op."""
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


class StubProvider(ActionProvider):
    def __init__(self, jobs, projects=None, projects_error=None):
        self._jobs = jobs
        self._projects = projects or []
        self._projects_error = projects_error

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return self._jobs

    def list_projects(self, reports_dir):
        if self._projects_error is not None:
            raise self._projects_error
        return {"projects": self._projects}


def _client(provider):
    return create_app(provider).test_client()


def _job(job_id: str, status: str = "running", project: str | None = None) -> JobSnapshot:
    return JobSnapshot(job_id=job_id, status=status, output_project=project)


def test_active_returns_null_when_nothing_is_running():
    client = _client(StubProvider([_job("j1", status="done")]))
    resp = client.get("/api/evaluations/active")
    assert resp.status_code == 200
    assert resp.get_json() is None


def test_active_returns_the_running_job_for_an_existing_project():
    client = _client(StubProvider(
        [_job("j1", project="proj-1")],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    ))
    resp = client.get("/api/evaluations/active")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["jobId"] == "j1"
    assert body["status"] == "running"
    assert body["outputProject"] == "proj-1"


def test_active_treats_running_job_of_deleted_project_as_stale():
    client = _client(StubProvider(
        [_job("j1", project="deleted-project")],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    ))
    resp = client.get("/api/evaluations/active")
    assert resp.status_code == 200
    assert resp.get_json() is None


def test_active_skips_stale_job_and_returns_the_next_valid_one():
    client = _client(StubProvider(
        [_job("j1", project="deleted-project"), _job("j2", project="proj-1")],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    ))
    resp = client.get("/api/evaluations/active")
    assert resp.get_json()["jobId"] == "j2"


def test_active_keeps_early_phase_job_without_output_project():
    client = _client(StubProvider([_job("j1", project=None)], projects=[]))
    resp = client.get("/api/evaluations/active")
    assert resp.get_json()["jobId"] == "j1"


def test_active_falls_back_to_first_running_job_when_projects_fail():
    client = _client(StubProvider(
        [_job("j1", project="anything")],
        projects_error=OSError("boom"),
    ))
    resp = client.get("/api/evaluations/active")
    assert resp.get_json()["jobId"] == "j1"


def test_active_is_not_shadowed_by_the_job_id_route():
    # /api/evaluations/<job_id> must not capture the static "active" segment.
    client = _client(StubProvider([]))
    resp = client.get("/api/evaluations/active")
    assert resp.status_code == 200
    assert resp.get_json() is None
