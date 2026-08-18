"""Concurrent misses on the read-through score caches must compute once.

Regression (v1.9.0 startup storm): after an upgrade invalidates every cached
row, the piled-up startup requests all miss the same (project, version) key
and each ran the full multi-minute recompute in parallel. The caches must
single-flight the compute so N concurrent misses cost one compute.
"""
from __future__ import annotations

import threading
import time

import pytest

from quodeq.services.score_cache import (
    cached_accumulated,
    cached_project_summary,
    open_score_cache,
)


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
