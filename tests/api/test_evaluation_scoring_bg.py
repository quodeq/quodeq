"""Regression test: GET /api/evaluations/<job_id> must not 500 when the
provider returns a job snapshot shape that doesn't guarantee a ``.job_id``
attribute (e.g. a dict-shaped snapshot) for a failed/cancelled job.

Guards routes_evaluations_item.py's _score_completed_dims_in_bg: it must use
the route's URL job_id (passed in explicitly) for _claim_scoring and the
background task name, never `job.job_id` — a job-snapshot-shaped object is
not guaranteed to carry that attribute, unlike the production JobSnapshot
dataclass.
"""
from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider
from tests._timeouts import budget


class _AttrDict(dict):
    """A dict that also supports attribute access to its keys.

    Models a job-snapshot shape that (unlike JobSnapshot) doesn't guarantee
    every attribute route code might reach for — in particular, no `job_id`
    key/attribute is set here, so `.job_id` raises AttributeError just like
    it would on a plain dict.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class _DictShapedFailedJobProvider(ActionProvider):
    """Minimal provider returning a dict-shaped, job_id-less failed job."""

    def list_projects(self, reports_dir):
        return {"projects": []}

    def get_project_info(self, reports_dir, project):
        return {}

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
        return {"jobId": "j1", "status": "failed", "logs": []}

    def get_evaluation_status(self, job_id, reports_dir=None):
        if job_id != "j1":
            return None
        return _AttrDict(
            status="failed",
            output_project="proj",
            output_run_id="run-1",
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


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    return create_app(_DictShapedFailedJobProvider()).test_client()


def test_get_evaluation_with_dict_shaped_failed_job_does_not_500(client):
    """A failed job whose snapshot lacks a `.job_id` attribute must not
    crash the GET — the route's URL job_id, not `job.job_id`, drives the
    background-scoring claim."""
    scoring_started = threading.Event()

    def _score(reports_dir, args):
        scoring_started.set()

    with patch(
        "quodeq.api._evaluation_routes.score_completed_evidence",
        side_effect=_score,
    ):
        resp = client.get("/api/evaluations/j1")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "failed"
    assert scoring_started.wait(timeout=budget(2)), (
        "Background scoring thread never started for the dict-shaped job."
    )
