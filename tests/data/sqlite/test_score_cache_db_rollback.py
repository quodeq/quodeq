"""A failed init step leaves no half-applied work on the score-cache connection."""
from __future__ import annotations

import sqlite3

from quodeq.data.sqlite import score_cache_schema
from quodeq.data.sqlite.score_cache_rows import RUN_SCALARS_COUNT_COLUMNS


class _FailingConn:
    """Wraps a real connection and raises on the *fail_on*-th matching call."""

    def __init__(self, conn: sqlite3.Connection, match: str, fail_on: int = 1) -> None:
        self._conn = conn
        self._match = match
        self._left = fail_on

    def _maybe_fail(self, sql: str) -> None:
        if self._match in sql:
            self._left -= 1
            if self._left == 0:
                raise sqlite3.OperationalError("disk I/O error")

    def execute(self, sql: str, *args):
        self._maybe_fail(sql)
        return self._conn.execute(sql, *args)

    def executemany(self, sql: str, *args):
        self._maybe_fail(sql)
        return self._conn.executemany(sql, *args)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def _stale_shape_cache(tmp_path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "cache.db")
    conn.executescript(score_cache_schema.SCHEMA)
    conn.execute("INSERT INTO run_keys VALUES ('p', 'r1', '[]', '[]')")
    conn.execute("INSERT INTO cache_meta VALUES ('run_keys_shape', 'old-shape')")
    conn.commit()
    return conn


def test_a_meta_sync_that_fails_after_the_purge_rolls_the_purge_back(tmp_path):
    conn = _stale_shape_cache(tmp_path)
    score_cache_schema.sync_cache_meta(_FailingConn(conn, "INSERT OR REPLACE INTO cache_meta"))
    assert not conn.in_transaction
    conn.commit()  # a later unrelated write must not carry the purge along
    assert conn.execute("SELECT count(*) FROM run_keys").fetchone()[0] == 1


def test_a_column_migration_that_fails_midway_adds_no_column(tmp_path):
    conn = sqlite3.connect(tmp_path / "cache.db")
    conn.execute("CREATE TABLE run_scalars (project TEXT, run_id TEXT)")
    conn.commit()
    score_cache_schema.ensure_run_scalars_columns(_FailingConn(conn, "ALTER TABLE", fail_on=2))
    assert not conn.in_transaction
    present = {row[1] for row in conn.execute("PRAGMA table_info(run_scalars)")}
    assert present.isdisjoint(RUN_SCALARS_COUNT_COLUMNS)


def test_a_column_migration_adds_every_missing_column(tmp_path):
    conn = sqlite3.connect(tmp_path / "cache.db")
    conn.execute("CREATE TABLE run_scalars (project TEXT, run_id TEXT)")
    conn.commit()
    score_cache_schema.ensure_run_scalars_columns(conn)
    present = {row[1] for row in conn.execute("PRAGMA table_info(run_scalars)")}
    assert set(RUN_SCALARS_COUNT_COLUMNS) <= present
