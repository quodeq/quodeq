import os
from pathlib import Path

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import (
    accumulated_cache_version,
    cached_accumulated,
    load_run_keys,
    open_score_cache,
    per_run_versions,
)


def test_version_changes_with_run_set(tmp_path):
    pd = tmp_path / "proj"; pd.mkdir()
    v1 = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], None)
    v2 = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete"), ("r2", "complete")], None)
    assert v1 != v2 and len(v1) == 64


def test_version_changes_with_status_and_as_of(tmp_path):
    pd = tmp_path / "proj"; pd.mkdir()
    base = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], None)
    assert accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "in_progress")], None) != base
    assert accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], "r1") != base


def test_version_stable_regardless_of_run_order(tmp_path):
    pd = tmp_path / "proj"; pd.mkdir()
    a = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete"), ("r2", "complete")], None)
    b = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r2", "complete"), ("r1", "complete")], None)
    assert a == b  # run-set is order-independent (sorted)


def test_version_folds_visible_dims_only_when_given(tmp_path):
    """visible_dims invalidates visibility-scoped payloads (project card) on a
    selection change, while None-passing callers (accumulated Overview, which
    returns every dim and lets the client filter) keep their hashes."""
    pd = tmp_path / "proj"; pd.mkdir()
    runs = [("r1", "complete")]
    base = accumulated_cache_version(pd, DEFAULT_PARAMS, runs, None)
    six = accumulated_cache_version(
        pd, DEFAULT_PARAMS, runs, None, visible_dims=("security", "reliability"))
    one = accumulated_cache_version(
        pd, DEFAULT_PARAMS, runs, None, visible_dims=("security",))
    assert len({base, six, one}) == 3
    # Selection is order-independent (sorted before hashing).
    assert six == accumulated_cache_version(
        pd, DEFAULT_PARAMS, runs, None, visible_dims=("reliability", "security"))


def test_cached_accumulated_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []
    def compute():
        calls.append(1)
        return {"dimensions": [], "summary": {"x": 1}}
    r1 = cached_accumulated("proj", "v1", compute)     # miss -> compute + cache
    r2 = cached_accumulated("proj", "v1", lambda: (_ for _ in ()).throw(AssertionError("recomputed on hit")))
    assert r1 == r2 == {"dimensions": [], "summary": {"x": 1}}
    assert calls == [1]


def test_per_run_versions_status_flip_reinvalidates(tmp_path, monkeypatch):
    """A run flipping in_progress -> complete must change the accumulated version.

    Regression: the scoped version hashes only params + intersecting suppressions
    (status-independent) and run_keys are frozen on first read, so without status
    folded into the accumulated fingerprint a run completing mid-poll would
    recompute the SAME version and serve a stale payload omitting that run.
    """
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    pd = tmp_path / "proj"; pd.mkdir()

    in_progress = per_run_versions(
        pd, "proj", DEFAULT_PARAMS, [("r1", "in_progress")], dismissed=set(), deleted=set())
    complete = per_run_versions(
        pd, "proj", DEFAULT_PARAMS, [("r1", "complete")], dismissed=set(), deleted=set())
    assert in_progress != complete  # status carried in the tuple

    v_ip = accumulated_cache_version(pd, DEFAULT_PARAMS, in_progress, None)
    v_c = accumulated_cache_version(pd, DEFAULT_PARAMS, complete, None)
    assert v_ip != v_c


def test_per_run_versions_does_not_persist_in_progress_keys(tmp_path, monkeypatch):
    """Non-terminal runs must not freeze a partial run_keys snapshot.

    Persisting an in-progress run's partial findings set would freeze it
    (load_run_keys short-circuits any re-read), so a suppression targeting a key
    that appears only after the run is observed mid-scan would silently
    under-invalidate.
    """
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    pd = tmp_path / "proj"; pd.mkdir()

    per_run_versions(
        pd, "proj", DEFAULT_PARAMS, [("r1", "in_progress")], dismissed=set(), deleted=set())
    with open_score_cache() as conn:
        assert load_run_keys(conn, "proj") == {}  # nothing persisted

    per_run_versions(
        pd, "proj", DEFAULT_PARAMS, [("r2", "complete")], dismissed=set(), deleted=set())
    with open_score_cache() as conn:
        assert "r2" in load_run_keys(conn, "proj")  # terminal run persisted


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based permission denial is ineffective as root or on Windows",
)
def test_per_run_versions_degrades_on_unopenable_cache(tmp_path, monkeypatch):
    """An unopenable score-cache dir must not turn this hot read path (called
    from scoring.get_project_scores / services._fs_metadata summaries) into a
    raise -- it must degrade to a fresh read_run_key_sets, same as any other
    disposable-cache failure.
    """
    pd = tmp_path / "proj"; pd.mkdir()
    ro_dir = tmp_path / "ro"; ro_dir.mkdir()
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(ro_dir / "sc.db"))
    os.chmod(ro_dir, 0o500)  # read+execute only: the db file can never be created
    try:
        out = per_run_versions(
            pd, "proj", DEFAULT_PARAMS, [("r1", "complete")], dismissed=set(), deleted=set())
    finally:
        os.chmod(ro_dir, 0o700)
    assert [(rid, status) for rid, status, _ in out] == [("r1", "complete")]


def test_cached_accumulated_not_cacheable_serves_without_persisting(tmp_path, monkeypatch):
    """A payload the caller flags as incomplete must be served but never written.

    Regression: a rescore built from a partial run read (1 of 6 dims in the
    process LRU) was persisted under a version hash identical to the complete
    payload's, so the half-rescored row was a permanent cache hit.
    """
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []
    def compute():
        calls.append(1)
        return {"dimensions": [], "summary": {"partial": True}}
    r1 = cached_accumulated("proj", "v1", compute, cacheable=lambda _p: False)
    assert r1 == {"dimensions": [], "summary": {"partial": True}}
    # Same version misses again: nothing was persisted.
    r2 = cached_accumulated("proj", "v1", compute, cacheable=lambda _p: False)
    assert r2 == r1
    assert calls == [1, 1]


def test_cached_accumulated_cacheable_true_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    calls = []
    def compute():
        calls.append(1)
        return {"dimensions": [], "summary": {"x": 1}}
    cached_accumulated("proj", "v1", compute, cacheable=lambda _p: True)
    r2 = cached_accumulated(
        "proj", "v1",
        lambda: (_ for _ in ()).throw(AssertionError("recomputed on hit")),
        cacheable=lambda _p: True,
    )
    assert r2 == {"dimensions": [], "summary": {"x": 1}}
    assert calls == [1]


def test_cached_accumulated_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    calls = []
    def compute():
        calls.append(1); return {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert calls == [1, 1]  # never cached
