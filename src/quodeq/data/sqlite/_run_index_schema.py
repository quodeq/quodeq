"""Schema DDL and open/migrate logic for the SQLite run index.

Split out of ``run_index.py`` purely to keep that module under the size
cap. ``open_index`` is re-exported from ``run_index`` -- that is the
stable public entry point callers use.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_BUSY_TIMEOUT_MS = 3000
# Bounded wait for the one lock SQLite will not route through busy_timeout --
# see _connect_retrying. The writer being waited on is a schema DDL that takes
# milliseconds, so this ceiling is never approached in practice; it is kept
# short so a wedged peer degrades the caller rather than stalling it.
_WAL_SWITCH_DEADLINE_S = 2.0
_WAL_SWITCH_SLEEP_S = 0.02

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
    # busy_timeout first so it governs every later statement, the journal_mode
    # switch included. It does not cover that switch completely -- see
    # _connect_retrying for the case it cannot absorb.
    db = sqlite3.connect(str(db_path))
    try:
        db.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        db.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        _close_quietly(db)
        raise
    return db


def _connect_retrying(db_path: Path) -> sqlite3.Connection:
    """Connect, waiting out the transient SQLITE_BUSY of the rollback->WAL switch.

    Only the first-ever connection to an index converts its journal to WAL,
    and SQLite refuses that conversion with ``OperationalError("database is
    locked")`` while another connection holds the file. Against a peer holding
    a *write* lock -- exactly what a concurrent ``_apply_schema_v1`` holds --
    that refusal is immediate: SQLite does not route it through the busy
    handler, so ``busy_timeout`` cannot absorb it. The peer is finishing a
    millisecond of schema DDL, so wait for it rather than reporting a
    perfectly healthy file as broken.
    """
    deadline = time.monotonic() + _WAL_SWITCH_DEADLINE_S
    while True:
        try:
            return _connect_with_pragmas(db_path)
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_WAL_SWITCH_SLEEP_S)


def _recreate_index_db(db_path: Path) -> sqlite3.Connection:
    """Delete *db_path* (with its WAL sidecars) and open a fresh connection.

    The ``-wal``/``-shm`` sidecars must go too: left next to a brand-new
    database file they describe content that no longer exists.
    """
    for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        path.unlink(missing_ok=True)
    return _connect_with_pragmas(db_path)


# Serializes open/create/rebuild per index file. Concurrent first-opens of a
# fresh index race the rollback->WAL switch above; the loser's SQLITE_BUSY is
# indistinguishable from corruption at this level, so the rebuild path used to
# unlink the file out from under the winner's live WAL connection. SQLite then
# treats the replacement file as a new database, zeroes the ``-shm`` wal-index
# the winner still has mmap'd, and the winner's next write dies with SIGBUS
# inside ``walIndexAppend``. Same bug, same shape as
# ``score_cache_db._OPEN_LOCK``; keyed by path here because ``open_index``
# takes one (``shared_repo.clone_lock`` is the registry precedent). Only
# open/rebuild is serialized -- the connections handed back stay concurrent.
_OPEN_LOCKS: dict[str, threading.Lock] = {}
_OPEN_LOCKS_GUARD = threading.Lock()


def _open_lock(db_path: Path) -> threading.Lock:
    """Return the process-wide lock for *db_path*, creating it on first use.

    Never pruned: a process opens the local index and at most a handful of
    shared-clone ones, so the registry stays a few entries deep.
    """
    with _OPEN_LOCKS_GUARD:
        return _OPEN_LOCKS.setdefault(str(db_path), threading.Lock())


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
    with _open_lock(db_path):
        return _open_or_rebuild(db_path)


def _open_or_rebuild(db_path: Path) -> sqlite3.Connection:
    """``open_index``'s body, run under that path's ``_open_lock``."""
    try:
        db = _connect_retrying(db_path)
    except sqlite3.OperationalError:
        # Lock contention or an I/O hiccup, NOT a bad file. Deleting a healthy
        # database that another connection still holds open is what crashed the
        # process with SIGBUS, so surface this and let the caller retry.
        raise
    except sqlite3.DatabaseError as exc:
        # Genuinely unusable bytes ("file is not a database", "database disk
        # image is malformed"): sqlite3 raises the DatabaseError base class for
        # those and never OperationalError, so the split above is exact.
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
