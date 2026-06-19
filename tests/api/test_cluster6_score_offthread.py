"""#1404 - _score_completed_evidence must run off the request thread.

The GET /api/evaluations/<id> handler should return immediately when a
job is failed/cancelled, without waiting for the (potentially slow) scoring
I/O to complete.
"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.api._evaluation_routes import (
    _claim_scoring,
    _scored_jobs,
    _scored_jobs_lock,
    _SCORED_JOBS_MAX,
)
from quodeq.services.base import ActionProvider, EvaluationOptions
from quodeq.services._job_model import JobSnapshot


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


@pytest.fixture()
def reports_root(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path))
    yield tmp_path


class _FailedJobProvider(ActionProvider):
    """Minimal provider returning a single 'failed' job."""

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
        return JobSnapshot(
            job_id="j1",
            status="failed",
            logs=[],
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


@pytest.fixture()
def client(reports_root):
    return create_app(_FailedJobProvider()).test_client()


def test_get_evaluation_returns_before_scoring_completes(client):
    """GET returns 200 without waiting for _score_completed_evidence to finish."""
    scoring_started = threading.Event()
    scoring_may_finish = threading.Event()

    def _slow_score(reports_dir, args):
        scoring_started.set()
        # Block until the test releases it — if the handler waited for this
        # the test would deadlock.
        scoring_may_finish.wait(timeout=5)

    with patch(
        "quodeq.api._evaluation_routes._score_completed_evidence",
        side_effect=_slow_score,
    ):
        resp = client.get("/api/evaluations/j1")

    # Response must have arrived before (or independently of) scoring finishing.
    assert resp.status_code == 200

    # Unblock the background thread so the test process can exit cleanly.
    scoring_may_finish.set()

    # Wait briefly for the thread to actually start, confirming it was launched.
    assert scoring_started.wait(timeout=2), (
        "Background scoring thread never started — check that the thread is "
        "actually launched in the handler."
    )


def test_get_evaluation_scores_only_once_for_same_job(client):
    """_score_completed_evidence is called at most once per job_id."""
    call_count = 0

    def _count_score(reports_dir, args):
        nonlocal call_count
        call_count += 1

    with patch(
        "quodeq.api._evaluation_routes._score_completed_evidence",
        side_effect=_count_score,
    ):
        client.get("/api/evaluations/j1")
        client.get("/api/evaluations/j1")
        # Give background threads time to finish.
        import time; time.sleep(0.1)

    assert call_count == 1, (
        f"Expected scoring to run exactly once (dedup via _scored_jobs), "
        f"got {call_count} calls."
    )


# ---------------------------------------------------------------------------
# Unit tests for _claim_scoring (race-closure + bounded-registry guarantees)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_claim_registry():
    """Ensure each test starts with a clean _scored_jobs registry."""
    with _scored_jobs_lock:
        _scored_jobs.clear()
    yield
    with _scored_jobs_lock:
        _scored_jobs.clear()


def test_claim_scoring_exactly_once_under_concurrency():
    """_claim_scoring returns True exactly once when N threads race on the same job_id.

    A threading.Barrier lines all N threads up so they enter _claim_scoring as
    simultaneously as possible, maximising the chance of exposing a race.
    Only one thread should win the claim; all others must get False.
    """
    n_threads = 10
    job_id = "race-job-concurrent"
    barrier = threading.Barrier(n_threads)
    results: list[bool] = []
    results_lock = threading.Lock()

    def _try_claim():
        barrier.wait()  # synchronize all threads to the same starting line
        claimed = _claim_scoring(job_id)
        with results_lock:
            results.append(claimed)

    threads = [threading.Thread(target=_try_claim) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(results) == n_threads, "Not all threads reported a result"
    true_count = sum(1 for r in results if r)
    assert true_count == 1, (
        f"Expected exactly 1 thread to win the claim, got {true_count}. "
        "TOCTOU race is still present."
    )


def test_claim_scoring_registry_bounded():
    """Registry never exceeds _SCORED_JOBS_MAX entries.

    Claims more than _SCORED_JOBS_MAX distinct job_ids and verifies that
    the registry size stays at or below the cap (oldest entries are evicted).
    """
    overflow = _SCORED_JOBS_MAX + 50
    for i in range(overflow):
        _claim_scoring(f"bounded-job-{i}")

    with _scored_jobs_lock:
        size = len(_scored_jobs)

    assert size <= _SCORED_JOBS_MAX, (
        f"Registry grew to {size}, exceeding the cap of {_SCORED_JOBS_MAX}. "
        "Memory leak is still present."
    )
