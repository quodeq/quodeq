"""Score-cache schema and the one-way migrations applied on every open.

:mod:`score_cache_db` owns the connection lifecycle; this module only knows
what the tables look like and how an older file is brought up to date.
"""
from __future__ import annotations

import logging
import sqlite3

from quodeq.data.sqlite._score_cache_epoch import (
    CACHE_WRITER_EPOCH, RUN_KEYS_SHAPE_SINCE_EPOCH, RUN_KEYS_SHAPE_VERSION,
)
from quodeq.data.sqlite.score_cache_rows import RUN_SCALARS_COLUMNS, column_type

_logger = logging.getLogger(__name__)


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS run_scalars ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL, version TEXT NOT NULL,"
    " dimension TEXT NOT NULL, overall_score TEXT, overall_grade TEXT,"
    " violation_count INTEGER, compliance_count INTEGER,"
    " critical INTEGER, major INTEGER, minor INTEGER, unknown INTEGER, open_types INTEGER,"
    " files_read INTEGER, source_file_count INTEGER, quarantined_count INTEGER,"
    " exit_reason TEXT, evidence_date TEXT, discipline TEXT,"
    " dismissed_count INTEGER, suppressed_count INTEGER,"
    " updated_at TEXT NOT NULL DEFAULT (datetime('now')),"
    " PRIMARY KEY (project, run_id, dimension, version));"
    "CREATE INDEX IF NOT EXISTS idx_run_scalars_lookup ON run_scalars(project, version);"
    "CREATE TABLE IF NOT EXISTS run_principle_scalars ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL, version TEXT NOT NULL,"
    " dimension TEXT NOT NULL, principle TEXT NOT NULL, score TEXT, grade TEXT, confidence TEXT,"
    " PRIMARY KEY (project, run_id, dimension, principle, version));"
    "CREATE INDEX IF NOT EXISTS idx_run_principle_scalars_lookup ON run_principle_scalars(project, version);"
    "DROP TABLE IF EXISTS accumulated_cache;"
    "CREATE TABLE IF NOT EXISTS project_summary_cache ("
    " project TEXT PRIMARY KEY, version TEXT NOT NULL, payload TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS run_keys ("
    " project TEXT NOT NULL, run_id TEXT NOT NULL,"
    " dismiss_keys TEXT NOT NULL, class_keys TEXT NOT NULL,"
    " PRIMARY KEY (project, run_id));"
    "CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
)


_META_WRITER_EPOCH = "writer_epoch"
_META_RUN_KEYS_SHAPE = "run_keys_shape"


def _meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM cache_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row is not None else None


def _stored_key_shape(conn: sqlite3.Connection) -> str | None:
    """The ``run_keys`` shape on disk; a cache from before the shape row infers it from its epoch."""
    shape = _meta_value(conn, _META_RUN_KEYS_SHAPE)
    if shape is not None:
        return shape
    epoch = _meta_value(conn, _META_WRITER_EPOCH)
    if epoch is not None and epoch.isdigit() and int(epoch) >= RUN_KEYS_SHAPE_SINCE_EPOCH:
        return RUN_KEYS_SHAPE_VERSION
    return None


def _rollback_quietly(conn: sqlite3.Connection) -> None:
    """Drop any pending transaction on *conn*; a failed rollback is only logged."""
    try:
        conn.rollback()
    except sqlite3.Error:
        _logger.debug("score cache rollback failed", exc_info=True)


def sync_cache_meta(conn: sqlite3.Connection) -> None:
    """Record the writer epoch, purging ``run_keys`` once when its shape changed.

    ``run_scalars`` / ``project_summary_cache`` embed the
    epoch in their version hash and self-invalidate on a bump. ``run_keys`` rows
    are not version-keyed, so a stale shape would stay frozen; they are purged
    when ``RUN_KEYS_SHAPE_VERSION`` changes, and kept across a payload-only
    epoch bump, since recomputing them hashes every finding of every run.
    """
    try:
        if _meta_value(conn, _META_WRITER_EPOCH) == CACHE_WRITER_EPOCH and \
                _meta_value(conn, _META_RUN_KEYS_SHAPE) == RUN_KEYS_SHAPE_VERSION:
            return
        if _stored_key_shape(conn) != RUN_KEYS_SHAPE_VERSION:
            conn.execute("DELETE FROM run_keys")
        conn.executemany(
            "INSERT OR REPLACE INTO cache_meta (key, value) VALUES (?, ?)",
            ((_META_WRITER_EPOCH, CACHE_WRITER_EPOCH), (_META_RUN_KEYS_SHAPE, RUN_KEYS_SHAPE_VERSION)),
        )
        conn.commit()
    except sqlite3.Error:
        # Roll back a purge whose meta write failed, so no later commit on
        # this connection can land it without the shape row it belongs to.
        _rollback_quietly(conn)
        _logger.warning("score cache meta sync failed", exc_info=True)


def ensure_run_scalars_columns(conn: sqlite3.Connection) -> None:
    """Add the columns a ``run_scalars`` table created before them lacks.

    ``CREATE TABLE IF NOT EXISTS`` leaves an existing table as it is, so an
    older cache file keeps its narrow table. The added columns are NULL on its
    old rows (which the epoch bump retires anyway) and stored on new ones.
    """
    try:
        present = {row[1] for row in conn.execute("PRAGMA table_info(run_scalars)")}
        missing = [c for c in RUN_SCALARS_COLUMNS if c not in present]
        if not missing:
            return
        # sqlite3 autocommits each DDL statement unless a transaction is
        # open; one explicit transaction makes the migration all-or-nothing.
        conn.execute("BEGIN")
        for column in missing:
            conn.execute(f"ALTER TABLE run_scalars ADD COLUMN {column} {column_type(column)}")
        conn.commit()
    except sqlite3.Error:
        _rollback_quietly(conn)
        _logger.warning("run_scalars column migration failed", exc_info=True)


def ensure_principle_confidence_column(conn: sqlite3.Connection) -> None:
    """Add ``confidence`` to a ``run_principle_scalars`` table created before it (NULL on old rows)."""
    try:
        present = {row[1] for row in conn.execute("PRAGMA table_info(run_principle_scalars)")}
        if "confidence" not in present:
            conn.execute("ALTER TABLE run_principle_scalars ADD COLUMN confidence TEXT")
            conn.commit()
    except sqlite3.Error:
        _rollback_quietly(conn)
        _logger.warning("run_principle_scalars column migration failed", exc_info=True)
