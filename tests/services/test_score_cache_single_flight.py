"""Concurrent misses on the read-through score caches must compute once.

Regression (v1.9.0 startup storm): after an upgrade invalidates every cached
row, the piled-up startup requests all miss the same (project, version) key
and each ran the full multi-minute recompute in parallel. The caches must
single-flight the compute so N concurrent misses cost one compute.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

import pytest

from quodeq.services.score_cache import (
    cached_accumulated,
    cached_project_summary,
    open_score_cache,
)
from quodeq.services.wiring import DEFAULT_SINGLE_FLIGHT, SingleFlight


def _race(n: int, call):
    """Run *call(i)* on n threads released together; return the results list."""
    barrier = threading.Barrier(n)
    results = [None] * n
    errors = []

    def run(i):
        barrier.wait()
        try:
            results[i] = call(i)
        except BaseException as exc:  # noqa: BLE001 — surfaced to the test
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def test_concurrent_accumulated_misses_compute_once(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []

    def compute():
        calls.append(1)
        time.sleep(0.05)
        return {"summary": {"x": 1}}

    results, errors = _race(3, lambda _i: cached_accumulated("proj", "v1", compute))

    assert not errors
    assert calls == [1], "concurrent misses on one key must share one compute"
    assert results == [{"summary": {"x": 1}}] * 3


def test_concurrent_summary_misses_compute_once(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []

    def compute():
        calls.append(1)
        time.sleep(0.05)
        return {"grade": "B"}

    results, errors = _race(3, lambda _i: cached_project_summary("proj", "v1", compute))

    assert not errors
    assert calls == [1]
    assert results == [{"grade": "B"}] * 3


def test_distinct_keys_still_compute_independently(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []

    def make_compute(tag):
        def compute():
            calls.append(tag)
            return {"summary": {"tag": tag}}
        return compute

    results, errors = _race(
        2, lambda i: cached_accumulated(f"proj-{i}", "v1", make_compute(i)),
    )

    assert not errors
    assert sorted(calls) == [0, 1], "different projects must not share a compute"
    assert results[0] != results[1]


def test_concurrent_first_open_initializes_safely(tmp_path, monkeypatch):
    """Racing first-opens of a fresh cache DB must not corrupt or crash.

    Regression: concurrent ``_init`` DDL on a brand-new file could raise a
    lock error that the rebuild path misread as corruption, unlinking the DB
    out from under another thread's live WAL connection (SIGBUS).
    """
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))

    def touch(_i):
        with open_score_cache() as conn:
            return conn.execute("SELECT count(*) FROM cache_meta").fetchone()[0]

    results, errors = _race(4, touch)

    assert not errors
    assert all(isinstance(r, int) for r in results)


def test_failed_compute_does_not_wedge_the_key(tmp_path, monkeypatch):
    """A compute that raises must release the in-flight key for the next caller."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))

    def boom():
        raise RuntimeError("compute failed")

    with pytest.raises(RuntimeError):
        cached_accumulated("proj", "v1", boom)

    out = cached_accumulated("proj", "v1", lambda: {"summary": {"ok": True}})
    assert out == {"summary": {"ok": True}}


# ---------------------------------------------------------------------------
# SingleFlight (the G3 process-scoped owner): low-level hold() semantics,
# event-based (no sleeps), plus proof the two public call paths share one
# process-wide instance (Review Focus 1).
# ---------------------------------------------------------------------------

class TestSingleFlightHold:
    def test_a_second_caller_for_the_same_key_waits_for_the_first(self):
        flight = SingleFlight()
        entered = threading.Event()
        release = threading.Event()
        order: list[str] = []

        def first():
            with flight.hold(("k",)):
                order.append("first-in")
                entered.set()
                assert release.wait(timeout=5), "first holder was never released"
                # Appended before the `with` exits (and so before hold()
                # releases the lock), so it happens-before the second caller
                # can possibly enter -- the ordering is guaranteed by the
                # lock itself, not by scheduling luck after the block exits.
                order.append("first-out")

        t1 = threading.Thread(target=first)
        t1.start()
        assert entered.wait(timeout=5), "first holder never entered"

        second_entered = threading.Event()

        def second():
            with flight.hold(("k",)):
                order.append("second-in")
                second_entered.set()

        t2 = threading.Thread(target=second)
        t2.start()
        # The second caller must not enter while the first still holds the key.
        assert not second_entered.wait(timeout=0.2), "second caller did not wait"

        release.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert order == ["first-in", "first-out", "second-in"]

    def test_distinct_keys_never_block_each_other(self):
        flight = SingleFlight()
        release = threading.Event()
        other_done = threading.Event()

        def holder():
            with flight.hold(("a",)):
                release.wait(timeout=5)

        t = threading.Thread(target=holder)
        t.start()
        try:
            with flight.hold(("b",)):
                other_done.set()
            assert other_done.is_set(), "a different key must not wait on key 'a'"
        finally:
            release.set()
            t.join(timeout=5)

    def test_a_released_key_leaves_no_lock_behind(self):
        """The per-key lock is dropped once no thread holds it, so the
        registry does not grow without bound across many distinct keys."""
        flight = SingleFlight()
        for i in range(5):
            with flight.hold((f"key-{i}",)):
                pass
        assert flight._locks == {}


def test_two_concurrent_misses_on_one_key_the_second_genuinely_waits(tmp_path, monkeypatch):
    """Event-based (no sleeps): the second caller for the SAME key must be
    genuinely blocked until the first compute finishes, not just lucky with
    timing -- this is what test_concurrent_accumulated_misses_compute_once
    above cannot distinguish from an unlucky race."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def compute():
        calls.append(1)
        entered.set()
        assert release.wait(timeout=5), "compute was never released"
        return {"summary": {"x": 1}}

    results: list[dict] = [None, None]

    def _first():
        results[0] = cached_accumulated("proj", "v1", compute)

    t1 = threading.Thread(target=_first)
    t1.start()
    assert entered.wait(timeout=5), "first compute never started"

    second_done = threading.Event()

    def _second():
        results[1] = cached_accumulated("proj", "v1", lambda: {"summary": {"x": 2}})
        second_done.set()

    t2 = threading.Thread(target=_second)
    t2.start()
    assert not second_done.wait(timeout=0.2), "second caller did not wait for the in-flight compute"

    release.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert calls == [1]
    assert results == [{"summary": {"x": 1}}, {"summary": {"x": 1}}]


def test_cached_accumulated_and_cached_project_summary_share_one_registry(tmp_path, monkeypatch):
    """Two different call paths (cached_accumulated, cached_project_summary)
    are different CacheSlot construction sites; both must resolve their
    default single_flight to the SAME process-wide instance, not one each."""
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    seen: list[tuple] = []
    real_hold = DEFAULT_SINGLE_FLIGHT.hold

    @contextmanager
    def spying_hold(key):
        seen.append(key)
        with real_hold(key):
            yield

    monkeypatch.setattr(DEFAULT_SINGLE_FLIGHT, "hold", spying_hold)
    cached_accumulated("proj", "v1", lambda: {"summary": {"x": 1}})
    cached_project_summary("proj", "v1", lambda: {"grade": "B"})

    assert seen == [("accumulated", "proj", "v1"), ("summary", "proj", "v1")]
