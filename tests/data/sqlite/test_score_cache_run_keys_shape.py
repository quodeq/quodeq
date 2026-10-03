"""Run key sets survive a payload epoch bump and are purged only on a shape change.

The key sets are the expensive part of a rebuild (every finding of every run
is hashed), and most epoch bumps change only the score rows. Purging them on
every bump made each upgrade recompute them for no reason.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.data.sqlite import score_cache_schema, score_cache_db
from quodeq.services.score_cache import open_score_cache


@pytest.fixture
def db_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "sc.db"
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(path))
    return path


def _store_a_key_row() -> None:
    with open_score_cache() as conn:
        conn.execute("INSERT INTO run_keys (project, run_id, dismiss_keys, class_keys) VALUES ('p', 'r', '[]', '[]')")
        conn.commit()


def _key_rows() -> int:
    with open_score_cache() as conn:
        return conn.execute("SELECT count(*) FROM run_keys").fetchone()[0]


def _meta(key: str) -> str | None:
    with open_score_cache() as conn:
        row = conn.execute("SELECT value FROM cache_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _bump_epoch(monkeypatch, epoch: str) -> None:
    """The epoch is bound in the open path (memo identity) and in the schema sync."""
    monkeypatch.setattr(score_cache_db, "CACHE_WRITER_EPOCH", epoch)
    monkeypatch.setattr(score_cache_schema, "CACHE_WRITER_EPOCH", epoch)


def test_a_payload_epoch_bump_keeps_the_key_sets(db_path, monkeypatch):
    _store_a_key_row()
    _bump_epoch(monkeypatch, "next-epoch")

    assert _key_rows() == 1
    assert _meta("writer_epoch") == "next-epoch"


def test_a_key_shape_bump_purges_the_key_sets(db_path, monkeypatch):
    _store_a_key_row()
    monkeypatch.setattr(score_cache_schema, "RUN_KEYS_SHAPE_VERSION", "next-shape")
    _bump_epoch(monkeypatch, "next-epoch")

    assert _key_rows() == 0
    assert _meta("run_keys_shape") == "next-shape"


def test_a_cache_from_before_the_shape_row_adopts_it_without_a_purge(db_path):
    """A cache written at epoch 7 or later already holds the current key shape."""
    _store_a_key_row()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM cache_meta WHERE key='run_keys_shape'")
        conn.execute("UPDATE cache_meta SET value='7' WHERE key='writer_epoch'")
    score_cache_db._forget(db_path)

    assert _key_rows() == 1
    assert _meta("run_keys_shape") == score_cache_schema.RUN_KEYS_SHAPE_VERSION


def test_a_cache_older_than_the_current_key_shape_is_purged(db_path):
    _store_a_key_row()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM cache_meta WHERE key='run_keys_shape'")
        conn.execute("UPDATE cache_meta SET value='6' WHERE key='writer_epoch'")
    score_cache_db._forget(db_path)

    assert _key_rows() == 0
