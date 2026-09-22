"""db_stamp() issues one stat() on the main db path, not two.

st.stat() already carries the file's type; a follow-up is_file() call
re-stats the same path just to ask a question the first stat answered.
"""
from __future__ import annotations

import os

from quodeq.data.sqlite._db_stamp_memo import (
    _DEFAULT_CACHE,
    _StampCache,
    db_stamp,
    memoized_by_db_stamp,
)


def test_db_stamp_stats_the_file_once(tmp_path, monkeypatch):
    db = tmp_path / "evaluation.db"
    db.write_bytes(b"x")
    calls = []
    real_stat = os.stat

    # Spy at the os.stat seam rather than Path.stat: Path.is_file() reaches
    # os.stat() either via Path.stat() or, on 3.14+, via os.path.isfile()
    # calling os.stat() directly -- Path.stat alone misses that second path.
    def counting_stat(path, *a, **k):
        calls.append(path)
        return real_stat(path, *a, **k)

    monkeypatch.setattr(os, "stat", counting_stat)
    assert db_stamp(db) is not None
    assert calls.count(db) == 1  # the WAL stat is a different path


def test_db_stamp_is_none_for_a_directory(tmp_path):
    assert db_stamp(tmp_path) is None


def test_db_stamp_is_none_for_a_missing_path(tmp_path):
    assert db_stamp(tmp_path / "nope.db") is None


def test_db_stamp_reflects_size_and_mtime(tmp_path):
    db = tmp_path / "evaluation.db"
    db.write_bytes(b"x")
    first = db_stamp(db)
    db.write_bytes(b"xy")
    second = db_stamp(db)
    assert first is not None and second is not None
    assert first != second


class TestMemoizedByDbStamp:
    """memoized_by_db_stamp reuses a result while the db is unchanged."""

    @staticmethod
    def _cache():
        return _StampCache()

    def test_second_call_reuses_the_first_result(self, tmp_path):
        db = tmp_path / "evaluation.db"
        db.write_bytes(b"x")
        cache = self._cache()
        calls = []

        def compute():
            calls.append(1)
            return {"n": len(calls)}

        assert memoized_by_db_stamp(db, compute, cache=cache) == {"n": 1}
        assert memoized_by_db_stamp(db, compute, cache=cache) == {"n": 1}
        assert len(calls) == 1

    def test_missing_db_returns_none_without_computing(self, tmp_path):
        calls = []
        result = memoized_by_db_stamp(
            tmp_path / "absent.db", lambda: calls.append(1), cache=self._cache())
        assert result is None
        assert calls == []

    def test_none_result_is_not_memoized(self, tmp_path):
        db = tmp_path / "evaluation.db"
        db.write_bytes(b"x")
        cache = self._cache()
        calls = []

        def compute():
            calls.append(1)
            return None if len(calls) == 1 else "ok"

        assert memoized_by_db_stamp(db, compute, cache=cache) is None
        assert memoized_by_db_stamp(db, compute, cache=cache) == "ok"

    def test_injected_cache_does_not_reach_the_default(self, tmp_path):
        db = tmp_path / "evaluation.db"
        db.write_bytes(b"x")
        memoized_by_db_stamp(db, lambda: "isolated", cache=self._cache())
        assert _DEFAULT_CACHE.get(str(db), db_stamp(db)) is None

    def test_clear_drops_the_memo(self, tmp_path):
        db = tmp_path / "evaluation.db"
        db.write_bytes(b"x")
        cache = self._cache()
        calls = []

        def compute():
            calls.append(1)
            return len(calls)

        assert memoized_by_db_stamp(db, compute, cache=cache) == 1
        cache.clear()
        assert memoized_by_db_stamp(db, compute, cache=cache) == 2
