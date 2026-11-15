"""RunChangeFiller: inline budget, one background worker, single-flight, failures cached."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from quodeq.services.run_log import FAILED_CHANGE, ChangeJob, RunChangeFiller
from quodeq.services.wiring import load_run_changes, open_score_cache, score_cache_path_override

WAIT_S = 10
KEY = "v|-"


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    # Create the cache here, outside every wait_idle: the first open of a file
    # writes the whole schema, and on a busy runner disk that alone outlasted
    # the wait when it fell to the background worker.
    with open_score_cache():
        pass


def _job(run_id: str) -> ChangeJob:
    return ChangeJob(Path("/nowhere"), "p", run_id, None, KEY)


def _stored(run_ids: list[str]) -> dict[str, dict]:
    with open_score_cache() as conn:
        return load_run_changes(conn, "p", dict.fromkeys(run_ids, KEY))


def test_a_failing_run_in_the_background_is_cached_as_failed_and_the_rest_still_fill() -> None:
    def compute(job: ChangeJob) -> dict:
        if job.run_id == "bad":
            raise ValueError("malformed report")
        return {"counts": {"new": 1}}

    filler = RunChangeFiller(budget_s=0.0)
    assert filler.fill([_job("bad"), _job("good")], compute) == {}
    assert filler.wait_idle(timeout=WAIT_S)
    assert _stored(["bad", "good"]) == {"bad": FAILED_CHANGE, "good": {"counts": {"new": 1}}}
    assert filler.pending("p") == set()


def test_a_run_already_in_flight_is_neither_computed_again_nor_queued_twice() -> None:
    gate = threading.Event()
    calls: list[str] = []

    def compute(job: ChangeJob) -> dict:
        calls.append(job.run_id)
        gate.wait(WAIT_S)
        return {}

    filler = RunChangeFiller(budget_s=0.0)
    filler.fill([_job("r1")], compute)
    assert filler.pending("p") == {"r1"}
    inline = filler.fill([_job("r1")], compute)
    gate.set()
    assert filler.wait_idle(timeout=WAIT_S)
    assert inline == {} and calls == ["r1"]


def test_the_inline_budget_computes_in_order_then_hands_off(monkeypatch) -> None:
    ticks = iter([0.0, 0.0, 0.5, 2.0, 2.0])
    filler = RunChangeFiller(budget_s=1.0, clock=lambda: next(ticks))
    done = filler.fill([_job("a"), _job("b"), _job("c")], lambda job: {"run": job.run_id})
    assert set(done) == {"a", "b"}
    assert filler.wait_idle(timeout=WAIT_S)
    assert _stored(["c"]) == {"c": {"run": "c"}}


def test_the_worker_writes_where_the_request_pointed_the_cache(tmp_path) -> None:
    shared = tmp_path / "shared.db"
    filler = RunChangeFiller(budget_s=0.0)
    with score_cache_path_override(shared):
        with open_score_cache():
            pass  # created before the worker's timed write, like the default cache
        filler.fill([_job("r1")], lambda job: {"shared": True})
    assert filler.wait_idle(timeout=WAIT_S)
    assert _stored(["r1"]) == {}
    with score_cache_path_override(shared), open_score_cache() as conn:
        assert load_run_changes(conn, "p", {"r1": KEY}) == {"r1": {"shared": True}}


def test_a_cache_os_error_in_the_worker_leaves_nothing_pending(monkeypatch) -> None:
    from contextlib import contextmanager  # noqa: PLC0415

    real_open = open_score_cache
    calls = {"n": 0}

    @contextmanager
    def flaky_open():
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("cache dir not creatable")
        with real_open() as conn:
            yield conn

    monkeypatch.setattr("quodeq.data.sqlite.score_cache_access.open_score_cache", flaky_open)
    filler = RunChangeFiller(budget_s=0.0)
    filler.fill([_job("r1"), _job("r2")], lambda job: {"run": job.run_id})
    assert filler.wait_idle(timeout=WAIT_S)
    assert filler.pending("p") == set()
    assert _stored(["r1", "r2"]) == {"r2": {"run": "r2"}}
    filler.fill([_job("r3")], lambda job: {"run": job.run_id})
    assert filler.wait_idle(timeout=WAIT_S)
    assert _stored(["r3"]) == {"r3": {"run": "r3"}}


def test_the_worker_does_not_use_the_requests_session_connection() -> None:
    from quodeq.services.wiring import score_cache_session  # noqa: PLC0415

    seen: list[object] = []

    def compute(job: ChangeJob) -> dict:
        with open_score_cache() as conn:
            seen.append(conn)
        return {}

    filler = RunChangeFiller(budget_s=0.0)
    with score_cache_session(), open_score_cache() as request_conn:
        filler.fill([_job("r1")], compute)
        assert filler.wait_idle(timeout=WAIT_S)
    assert seen and seen[0] is not request_conn
