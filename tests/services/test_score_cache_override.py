"""Score cache path override for the shared root."""
from __future__ import annotations

import pytest

from quodeq.services.score_cache import open_score_cache, score_cache_path_override


def test_override_redirects_db_path(tmp_path, monkeypatch):
    override_db = tmp_path / "shared" / "score_cache.db"
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    with score_cache_path_override(override_db):
        with open_score_cache() as conn:
            pass
    assert override_db.exists()
    # Nothing was written to the default (non-override) location.
    assert not (tmp_path / "score_cache.db").exists()


def test_no_override_uses_default(tmp_path, monkeypatch):
    # Point the default location into tmp so the test never touches ~/.quodeq.
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    with open_score_cache() as conn:
        pass
    assert not (tmp_path / "shared").exists()
    assert (tmp_path / "score_cache.db").exists()


def test_override_restored_after_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    override_db = tmp_path / "shared" / "score_cache.db"
    with pytest.raises(RuntimeError):
        with score_cache_path_override(override_db):
            raise RuntimeError("boom")
    with open_score_cache() as conn:
        pass
    # After the exception, the override must be cleared: the default path
    # (next to the tmp index db) is used, not the override target.
    assert (tmp_path / "score_cache.db").exists()


def test_nested_override_restores_outer(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    outer_db = tmp_path / "outer" / "score_cache.db"
    inner_db = tmp_path / "inner" / "score_cache.db"
    with score_cache_path_override(outer_db):
        with score_cache_path_override(inner_db):
            with open_score_cache() as conn:
                pass
        assert inner_db.exists()
        with open_score_cache() as conn:
            pass
    assert outer_db.exists()
