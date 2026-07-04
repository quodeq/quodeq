import dataclasses
from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import score_cache_version


def test_stable_for_same_inputs(tmp_path, monkeypatch):
    pd = tmp_path / "proj"
    pd.mkdir()
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: {("R1", "a.py", 1)})
    monkeypatch.setattr("quodeq.services.score_cache.deleted_keys", lambda _p: set())
    v1 = score_cache_version(pd, DEFAULT_PARAMS)
    v2 = score_cache_version(pd, DEFAULT_PARAMS)
    assert v1 == v2 and len(v1) == 64  # sha256 hex


def test_changes_when_dismissals_change(tmp_path, monkeypatch):
    pd = tmp_path / "proj"; pd.mkdir()
    monkeypatch.setattr("quodeq.services.score_cache.deleted_keys", lambda _p: set())
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: {("R1", "a.py", 1)})
    v1 = score_cache_version(pd, DEFAULT_PARAMS)
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: {("R1", "a.py", 1), ("R2", "b.py", 2)})
    v2 = score_cache_version(pd, DEFAULT_PARAMS)
    assert v1 != v2


def test_changes_when_writer_epoch_changes(tmp_path, monkeypatch):
    """The writer epoch participates in the version.

    Bumping it invalidates every row written by a prior writer -- the one-time
    repair for runs whose partial (in-progress) scalar set was persisted before
    the write-guard existed. They miss on the next build and are rebuilt fresh.
    """
    pd = tmp_path / "proj"; pd.mkdir()
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: set())
    monkeypatch.setattr("quodeq.services.score_cache.deleted_keys", lambda _p: set())
    v1 = score_cache_version(pd, DEFAULT_PARAMS)
    monkeypatch.setattr("quodeq.services.score_cache._CACHE_WRITER_EPOCH", "different-epoch")
    v2 = score_cache_version(pd, DEFAULT_PARAMS)
    assert v1 != v2


def test_changes_when_params_change(tmp_path, monkeypatch):
    pd = tmp_path / "proj"; pd.mkdir()
    monkeypatch.setattr("quodeq.services.score_cache.dismissed_keys", lambda _p: set())
    monkeypatch.setattr("quodeq.services.score_cache.deleted_keys", lambda _p: set())
    v1 = score_cache_version(pd, DEFAULT_PARAMS)
    strict = dataclasses.replace(DEFAULT_PARAMS, base_k=DEFAULT_PARAMS.base_k + 1.0)
    v2 = score_cache_version(pd, strict)
    assert v1 != v2
