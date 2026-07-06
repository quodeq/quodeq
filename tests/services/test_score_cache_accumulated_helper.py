from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import (
    accumulated_cache_version,
    cached_accumulated,
    load_run_keys,
    open_score_cache,
    per_run_versions,
)


def _patch_keys(monkeypatch, dismissed=frozenset(), deleted=frozenset()):
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: set(dismissed))
    monkeypatch.setattr("quodeq.services.score_cache.deleted_keys", lambda _p: set(deleted))


def test_version_changes_with_run_set(tmp_path, monkeypatch):
    _patch_keys(monkeypatch)
    pd = tmp_path / "proj"; pd.mkdir()
    v1 = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], None)
    v2 = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete"), ("r2", "complete")], None)
    assert v1 != v2 and len(v1) == 64


def test_version_changes_with_status_and_as_of(tmp_path, monkeypatch):
    _patch_keys(monkeypatch)
    pd = tmp_path / "proj"; pd.mkdir()
    base = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], None)
    assert accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "in_progress")], None) != base
    assert accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete")], "r1") != base


def test_version_stable_regardless_of_run_order(tmp_path, monkeypatch):
    _patch_keys(monkeypatch)
    pd = tmp_path / "proj"; pd.mkdir()
    a = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r1", "complete"), ("r2", "complete")], None)
    b = accumulated_cache_version(pd, DEFAULT_PARAMS, [("r2", "complete"), ("r1", "complete")], None)
    assert a == b  # run-set is order-independent (sorted)


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
    _patch_keys(monkeypatch)
    pd = tmp_path / "proj"; pd.mkdir()

    in_progress = per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "in_progress")])
    complete = per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "complete")])
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
    _patch_keys(monkeypatch)
    pd = tmp_path / "proj"; pd.mkdir()

    per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r1", "in_progress")])
    with open_score_cache() as conn:
        assert load_run_keys(conn, "proj") == {}  # nothing persisted

    per_run_versions(pd, "proj", DEFAULT_PARAMS, [("r2", "complete")])
    with open_score_cache() as conn:
        assert "r2" in load_run_keys(conn, "proj")  # terminal run persisted


def test_cached_accumulated_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    calls = []
    def compute():
        calls.append(1); return {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert calls == [1, 1]  # never cached
