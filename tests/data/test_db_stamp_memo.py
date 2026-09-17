"""db_stamp() issues one stat() on the main db path, not two.

st.stat() already carries the file's type; a follow-up is_file() call
re-stats the same path just to ask a question the first stat answered.
"""
from __future__ import annotations

import os

from quodeq.data.sqlite._db_stamp_memo import db_stamp


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
