from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import accumulated_cache_version, cached_accumulated


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


def test_cached_accumulated_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
    calls = []
    def compute():
        calls.append(1); return {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert cached_accumulated("proj", "v1", compute) == {"y": 2}
    assert calls == [1, 1]  # never cached
