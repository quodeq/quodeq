"""Schema DDL and open/migrate logic for the SQLite run index.

Split out of ``run_index.py`` purely to keep that module under the size
cap. ``open_index`` is re-exported from ``run_index`` -- that is the
stable public entry point callers use.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS runs (
    job_id            TEXT PRIMARY KEY,
    project_uuid      TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    run_dir           TEXT NOT NULL,
    state             TEXT NOT NULL,
    phase             TEXT,
    current_dimension TEXT,
    started_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    finalized_at      TEXT,
    heartbeat_at      TEXT,
    pid               INTEGER,
    exit_reason       TEXT,
    status_mtime      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_state      ON runs(state);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""


def _apply_schema_v1(db: sqlite3.Connection) -> None:
    with db:
        db.executescript(_SCHEMA_V1)
        have_version = db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        if have_version == 0:
            db.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))


def _read_schema_version(db: sqlite3.Connection) -> int | None:
    try:
        row = db.execute("SELECT version FROM schema_version").fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None:
        return None
    return int(row[0])


def _close_quietly(db: sqlite3.Connection) -> None:
    # Windows holds a file handle while the connection is open, so a
    # subsequent unlink would raise PermissionError unless closed first.
    try:
        db.close()
    except sqlite3.Error:
        pass


def _connect_with_pragmas(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path))
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=3000")
    except sqlite3.DatabaseError:
        _close_quietly(db)
        raise
    return db


def _recreate_index_db(db_path: Path) -> sqlite3.Connection:
    """Delete *db_path* and open a fresh connection with pragmas applied."""
    db_path.unlink(missing_ok=True)
    return _connect_with_pragmas(db_path)


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the index DB at *db_path*, migrate to current schema.

    The index is derived state — rebuildable from the run files on disk — so a
    DB this binary can't use is discarded and recreated rather than fatal:

    * a corrupt/unreadable file, or
    * a downgraded index whose ``schema_version`` is newer than we support
      (the user ran a newer quodeq, then installed an older one).

    Either way the next ``sync_index`` repopulates it from disk.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        db = _connect_with_pragmas(db_path)
    except sqlite3.DatabaseError as exc:
        _logger.warning("index DB at %s is corrupt (%s) — recreating", db_path, exc)
        db = _recreate_index_db(db_path)

    version = _read_schema_version(db)
    if version is None:
        _apply_schema_v1(db)
        return db
    if version > SCHEMA_VERSION:
        # Downgrade: a newer quodeq migrated the index forward. It's a derived
        # projection, so discard and rebuild rather than crash — mirrors the
        # corrupt-file recovery above. The next sync_index repopulates it.
        _logger.warning(
            "index DB at %s has schema_version=%s newer than supported (%s) — "
            "rebuilding from run files", db_path, version, SCHEMA_VERSION,
        )
        _close_quietly(db)
        db = _recreate_index_db(db_path)
        _apply_schema_v1(db)
        return db
    return db
