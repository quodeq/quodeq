"""A running eval must not turn every accumulated read into a full recompute.

Regression (2026-09-23): the accumulated version folds in the in-progress
run's key set, so every finding the eval writes re-keys the cache. Each
/scores request missed, recomputed the whole history (~30s idle, far longer
under eval load) and single-flight could not help because the version kept
moving. The UI's 15s error retries stacked ~90 concurrent computes and every
dashboard read timed out. Within one stale scope (same runs, statuses and
suppressions; only in-flight runs' keys differ) a miss now serves the last
payload and refreshes it once in the background.
"""
from __future__ import annotations

import threading
import time

import pytest

from quodeq.core.run.state import RunState
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import accumulated_stale_scope, cached_accumulated


@pytest.fixture(autouse=True)
def _cache_db(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_version_churn_serves_last_payload_and_refreshes_once():
    cached_accumulated("proj", "v1", lambda: {"n": 1}, stale_scope="s")

    release = threading.Event()
    calls = []

    def slow_compute():
        calls.append(1)
        release.wait(5)
        return {"n": 2}

    started = time.monotonic()
    results = [cached_accumulated("proj", f"v{i}", slow_compute, stale_scope="s") for i in range(2, 7)]
    elapsed = time.monotonic() - started

    assert results == [{"n": 1}] * 5, "churned versions must serve the last payload"
    assert elapsed < 1.0, "a stale read must not wait for the refresh"
    assert _wait_for(lambda: calls == [1]), "one background refresh, not one per request"

    release.set()
    # The refresh ran for the first churned version and persisted it.
    assert _wait_for(lambda: cached_accumulated("proj", "v2", slow_compute, stale_scope="s") == {"n": 2})
    assert calls == [1]


def test_scope_change_computes_synchronously():
    cached_accumulated("proj", "v1", lambda: {"n": 1}, stale_scope="s1")

    out = cached_accumulated("proj", "v2", lambda: {"n": 2}, stale_scope="s2")

    assert out == {"n": 2}, "a new scope (dismiss, finished run) must not serve stale data"


def test_exact_hit_skips_refresh():
    cached_accumulated("proj", "v1", lambda: {"n": 1}, stale_scope="s")
    calls = []

    out = cached_accumulated("proj", "v1", lambda: calls.append(1) or {"n": 2}, stale_scope="s")

    assert out == {"n": 1}
    time.sleep(0.05)
    assert calls == []


def test_failed_refresh_keeps_stale_payload_and_frees_the_slot():
    cached_accumulated("proj", "v1", lambda: {"n": 1}, stale_scope="s")
    failed = threading.Event()

    def boom():
        failed.set()
        raise OSError("compute failed")

    assert cached_accumulated("proj", "v2", boom, stale_scope="s") == {"n": 1}
    assert failed.wait(5)

    assert _wait_for(lambda: cached_accumulated("proj", "v3", lambda: {"n": 3}, stale_scope="s") == {"n": 3}), \
        "a failed refresh must release the slot for the next one"


def test_without_scope_a_miss_still_computes():
    cached_accumulated("proj", "v1", lambda: {"n": 1})

    assert cached_accumulated("proj", "v2", lambda: {"n": 2}) == {"n": 2}


_PARAMS = DEFAULT_PARAMS


def _scope(runs, fp="fp", as_of=None):
    return accumulated_stale_scope(_PARAMS, runs, as_of, fp)


@pytest.mark.parametrize("status", [RunState.PENDING, RunState.RUNNING, RunState.FINALIZING])
def test_scope_ignores_in_flight_run_keys(status):
    done = ("r1", RunState.DONE, "a")
    assert _scope([done, ("r2", status, "x")]) == _scope([done, ("r2", status, "y")])


def test_scope_tracks_everything_else():
    base = [("r1", RunState.DONE, "a"), ("r2", RunState.RUNNING, "x")]
    variants = [
        [("r1", RunState.DONE, "b"), ("r2", RunState.RUNNING, "x")],   # a done run's version moved
        [("r1", RunState.DONE, "a"), ("r2", RunState.DONE, "x")],      # the running run finished
        [("r1", RunState.DONE, "a")],                                  # a run disappeared
    ]
    for runs in variants:
        assert _scope(runs) != _scope(base)
    assert _scope(base, fp="other") != _scope(base), "a dismiss/delete must change the scope"
    assert _scope(base, as_of="r1") != _scope(base)
