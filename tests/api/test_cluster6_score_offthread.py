"""#1404 - _score_completed_evidence must run off the request thread.

The GET /api/evaluations/<id> handler should return immediately when a
job is failed/cancelled, without waiting for the (potentially slow) scoring
I/O to complete.
"""
from __future__ import annotations

import logging
import threading
import time
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.services.scored_jobs_registry import ScoringClaims, SCORED_JOBS_MAX
from quodeq.services.base import ActionProvider
from quodeq.services._job_model import JobSnapshot
from tests._timeouts import budget


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
        scoring_may_finish.wait(timeout=budget(5))

    with patch(
        "quodeq.services.score_run.score_completed_evidence",
        side_effect=_slow_score,
    ):
        resp = client.get("/api/evaluations/j1")

    # Response must have arrived before (or independently of) scoring finishing.
    assert resp.status_code == 200

    # Unblock the background thread so the test process can exit cleanly.
    scoring_may_finish.set()

    # Wait briefly for the thread to actually start, confirming it was launched.
    assert scoring_started.wait(timeout=budget(2)), (
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
        "quodeq.services.score_run.score_completed_evidence",
        side_effect=_count_score,
    ):
        client.get("/api/evaluations/j1")
        client.get("/api/evaluations/j1")
        # Give background threads time to finish.
        time.sleep(0.1)

    assert call_count == 1, (
        f"Expected scoring to run exactly once (dedup via ScoringClaims), "
        f"got {call_count} calls."
    )


def test_score_completed_dims_failure_is_isolated_and_logged(client, caplog):
    """A raising scorer is isolated and logged with its traceback."""
    with patch(
        "quodeq.services.score_run.score_completed_evidence",
        side_effect=RuntimeError("boom"),
    ), caplog.at_level(logging.WARNING, logger="quodeq.services.score_run"):
        resp = client.get("/api/evaluations/j1")

        deadline = time.monotonic() + budget(5)
        while time.monotonic() < deadline and not caplog.records:
            time.sleep(0.02)

    assert resp.status_code == 200
    matching = [r for r in caplog.records if "failed" in r.getMessage()]
    assert matching, [r.getMessage() for r in caplog.records]
    assert any(r.exc_info for r in matching)


class _DeadlineCancelledProvider(_FailedJobProvider):
    """Deadline-killed job: status 'cancelled' with exit_reason 'deadline'."""

    def get_evaluation_status(self, job_id, reports_dir=None):
        if job_id != "j1":
            return None
        return JobSnapshot(
            job_id="j1",
            status="cancelled",
            exit_reason="deadline",
            logs=[],
            output_project="proj",
            output_run_id="run-1",
        )


def test_deadline_cancelled_job_still_triggers_salvage_scoring(reports_root):
    """Guards the deadline-exit design in services/jobs.py: watchdog-killed
    jobs end as status='cancelled' (+ exit_reason='deadline') and rely on
    'cancelled' staying in this route's salvage-scoring trigger list.
    """
    client = create_app(_DeadlineCancelledProvider()).test_client()
    scoring_started = threading.Event()

    def _score(reports_dir, args):
        scoring_started.set()

    with patch(
        "quodeq.services.score_run.score_completed_evidence",
        side_effect=_score,
    ):
        resp = client.get("/api/evaluations/j1")

    assert resp.status_code == 200
    # The UI reads exitReason off this payload to render "time limit reached".
    assert resp.get_json().get("exitReason") == "deadline"
    assert scoring_started.wait(timeout=budget(2)), (
        "Deadline-cancelled job never spawned salvage scoring — did "
        "'cancelled' fall out of the trigger list in _evaluation_routes?"
    )


# ScoringClaims unit tests: each builds its own instance, so nothing to reset.

def test_claim_scoring_exactly_once_under_concurrency():
    """claim() returns True exactly once when N threads race on the same job_id.

    A threading.Barrier lines all N threads up so they enter claim() as
    simultaneously as possible, maximising the chance of exposing a race.
    Only one thread should win the claim; all others must get False.
    """
    claims = ScoringClaims()
    n_threads = 10
    job_id = "race-job-concurrent"
    barrier = threading.Barrier(n_threads)
    results: list[bool] = []
    results_lock = threading.Lock()

    def _try_claim():
        barrier.wait()  # synchronize all threads to the same starting line
        claimed = claims.claim(job_id)
        with results_lock:
            results.append(claimed)

    threads = [threading.Thread(target=_try_claim) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=budget(5))

    assert len(results) == n_threads, "Not all threads reported a result"
    true_count = sum(1 for r in results if r)
    assert true_count == 1, (
        f"Expected exactly 1 thread to win the claim, got {true_count}. "
        "TOCTOU race is still present."
    )


def test_claim_scoring_registry_bounded():
    """Registry never exceeds SCORED_JOBS_MAX entries (oldest are evicted)."""
    claims = ScoringClaims()
    overflow = SCORED_JOBS_MAX + 50
    for i in range(overflow):
        claims.claim(f"bounded-job-{i}")

    size = len(claims)

    assert size <= SCORED_JOBS_MAX, (
        f"Registry grew to {size}, exceeding the cap of {SCORED_JOBS_MAX}. "
        "Memory leak is still present."
    )


def test_claim_scoring_evicts_oldest_first_like_the_old_ordereddict():
    """LRU eviction order: overflowing by one drops the earliest-claimed
    job_id, not an arbitrary one. Matches the old OrderedDict's
    ``popitem(last=False)`` (insertion-order, not access-order, eviction).
    """
    claims = ScoringClaims(max_entries=3)
    for job_id in ("a", "b", "c"):
        assert claims.claim(job_id)

    assert claims.claim("d")  # overflow by one: "a" (oldest) must be evicted

    assert len(claims) == 3
    # Check the still-claimed ids first: claim() returning False never
    # mutates, so checking these first avoids a second eviction from the
    # "a" re-claim below skewing which id "was evicted" means.
    assert not claims.claim("b")  # "b" is still claimed
    assert not claims.claim("c")  # "c" is still claimed
    assert not claims.claim("d")  # "d" is still claimed
    assert claims.claim("a")  # "a" was evicted by the overflow, so claimable again


def test_release_allows_a_reclaim():
    claims = ScoringClaims()
    assert claims.claim("j1")
    assert not claims.claim("j1")  # already claimed

    claims.release("j1")

    assert claims.claim("j1")  # released, so claimable again


def test_reset_clears_every_claim():
    claims = ScoringClaims()
    claims.claim("j1")
    claims.claim("j2")

    claims.reset()

    assert len(claims) == 0
    assert claims.claim("j1")
    assert claims.claim("j2")
