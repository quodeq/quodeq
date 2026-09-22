"""Unit tests for services.active_evaluation.find_active_evaluation.

The staleness rule moved here verbatim from
dashboard/_webview_window._WindowApi._get_running_evaluation, so these tests
pin exactly the behavior that function used to implement: a "running" job
whose outputProject is missing from the project list is stale and skipped,
jobs without an outputProject stay valid, and a failing project lookup falls
back to the first running job.
"""
from __future__ import annotations

import pytest

from quodeq.core.types import JobSnapshot, ProjectEntry
from quodeq.services.active_evaluation import find_active_evaluation

_REPORTS = "/tmp/reports"


class StubProvider:
    def __init__(self, jobs, projects=None, projects_error=None):
        self._jobs = jobs
        self._projects = projects or []
        self._projects_error = projects_error
        self.list_projects_calls = 0

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return self._jobs

    def list_projects(self, reports_dir):
        self.list_projects_calls += 1
        if self._projects_error is not None:
            raise self._projects_error
        return {"projects": self._projects}


def _job(job_id: str, status: str = "running", project: str | None = None) -> JobSnapshot:
    return JobSnapshot(job_id=job_id, status=status, output_project=project)


def test_no_running_jobs_returns_none_without_touching_projects():
    provider = StubProvider([_job("j1", status="done"), _job("j2", status="failed")])
    assert find_active_evaluation(provider, _REPORTS) is None
    assert provider.list_projects_calls == 0


def test_running_job_with_existing_project_is_returned_as_produced():
    running = _job("j1", project="proj-1")
    provider = StubProvider(
        [running],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    )
    assert find_active_evaluation(provider, _REPORTS) is running


def test_running_job_with_deleted_project_is_stale():
    provider = StubProvider(
        [_job("j1", project="gone")],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    )
    assert find_active_evaluation(provider, _REPORTS) is None


def test_stale_job_is_skipped_in_favor_of_a_valid_one():
    provider = StubProvider(
        [_job("j1", project="gone"), _job("j2", project="proj-1")],
        projects=[ProjectEntry(id="proj-1", name="Proj")],
    )
    job = find_active_evaluation(provider, _REPORTS)
    assert job is not None and job.job_id == "j2"


def test_job_without_output_project_is_treated_as_valid():
    # Very-early-phase evals haven't registered an output yet.
    provider = StubProvider([_job("j1", project=None)], projects=[])
    job = find_active_evaluation(provider, _REPORTS)
    assert job is not None and job.job_id == "j1"


def test_projects_failure_falls_back_to_first_running_job():
    provider = StubProvider(
        [_job("j1", project="gone")],
        projects_error=OSError("projects listing broke"),
    )
    job = find_active_evaluation(provider, _REPORTS)
    assert job is not None and job.job_id == "j1"


def test_dict_jobs_and_dict_projects_are_supported():
    # Remote/stub providers hand back wire dicts; the rule reads the same
    # keys the webview used to read ("project" as the legacy fallback).
    provider = StubProvider(
        [{"jobId": "j1", "status": "running", "project": "proj-1"}],
        projects=[{"id": "proj-1", "name": "Proj"}],
    )
    job = find_active_evaluation(provider, _REPORTS)
    assert job is not None and job["jobId"] == "j1"


@pytest.mark.parametrize("items", [None, {}, "nonsense"])
def test_non_list_evaluations_payload_yields_none(items):
    provider = StubProvider(items)
    assert find_active_evaluation(provider, _REPORTS) is None
