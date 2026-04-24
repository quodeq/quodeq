# src/quodeq/services/run_index.py
"""SQLite-backed run index.

The index is **derived state** — rebuildable at any time from the filesystem
(``~/.quodeq/evaluations/**/status.json`` and legacy signals). Delete
``~/.quodeq/index.db`` at any time; the next ``open_index`` creates an empty
database and the next ``sync_index`` call repopulates.

Public API is the only stable surface — internals live in ``_index_sync``.
"""
from __future__ import annotations

import logging
import sqlite3
import time as _time
from dataclasses import dataclass
from pathlib import Path

from quodeq.services._index_sync import (
    _check_stale_and_promote,
    _sync_legacy_run,
    _upsert_from_status,
    _status_mtime_ns,
)

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class UnsupportedIndexSchemaError(RuntimeError):
    """Raised when index.db has schema_version > SCHEMA_VERSION."""


@dataclass(frozen=True)
class RunRow:
    """One row of the runs table, as a plain dataclass."""

    job_id: str
    project_uuid: str
    run_id: str
    run_dir: str
    state: str
    phase: str | None
    current_dimension: str | None
    started_at: str
    updated_at: str
    finalized_at: str | None
    heartbeat_at: str | None
    pid: int | None
    exit_reason: str | None
    status_mtime: int


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


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open (or create) the index DB at *db_path*, migrate to current schema.

    Raises UnsupportedIndexSchemaError if the existing DB has a newer schema.
    Recovers from a corrupt file by deleting and recreating.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        db = sqlite3.connect(str(db_path))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=3000")
    except sqlite3.DatabaseError as exc:
        _logger.warning("index DB at %s is corrupt (%s) — recreating", db_path, exc)
        db_path.unlink(missing_ok=True)
        db = sqlite3.connect(str(db_path))
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=3000")

    version = _read_schema_version(db)
    if version is None:
        _apply_schema_v1(db)
        return db
    if version > SCHEMA_VERSION:
        db.close()
        raise UnsupportedIndexSchemaError(
            f"index schema_version={version} newer than supported ({SCHEMA_VERSION})"
        )
    return db


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _walk_run_dirs(evaluations_root: Path):
    """Yield (project_uuid, run_id, run_dir) for every run on disk."""
    if not evaluations_root.is_dir():
        return
    for project_dir in evaluations_root.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        for run_dir in project_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            yield project_dir.name, run_dir.name, run_dir


def _sync_one_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    status_path = run_dir / "status.json"
    if status_path.exists():
        disk_mtime = _status_mtime_ns(run_dir)
        job_id = f"ext-{run_id}"
        cached = db.execute(
            "SELECT status_mtime FROM runs WHERE job_id = ?", (job_id,),
        ).fetchone()
        if cached is None or cached[0] != disk_mtime:
            try:
                _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
            except Exception as exc:
                _logger.warning("skipping run %s: %s", run_dir, exc)
                return
        # Always check staleness, even on mtime-unchanged runs.
        try:
            _check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("stale-check failed for %s: %s", run_dir, exc)
    else:
        try:
            _sync_legacy_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("legacy sync failed for %s: %s", run_dir, exc)


# ---------------------------------------------------------------------------
# Public sync API
# ---------------------------------------------------------------------------

def sync_index(db: sqlite3.Connection, evaluations_root: Path) -> None:
    """Lazy upsert: walk *evaluations_root*, sync any run whose status.json
    changed since last seen OR that lacks an index row entirely. Promote
    stale non-terminal runs.
    """
    for project_uuid, run_id, run_dir in _walk_run_dirs(evaluations_root):
        _sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def sync_index_for_run(db: sqlite3.Connection, run_dir: Path) -> None:
    """Sync only the given run_dir (used by /api/evaluations/<id>)."""
    if not run_dir.is_dir():
        return
    project_uuid = run_dir.parent.name
    run_id = run_dir.name
    _sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

_LIST_COLS = (
    "job_id, project_uuid, run_id, run_dir, state, phase, current_dimension, "
    "started_at, updated_at, finalized_at, heartbeat_at, pid, exit_reason, status_mtime"
)


def _row_to_runrow(row: tuple) -> RunRow:
    return RunRow(*row)


def list_runs(db: sqlite3.Connection, *, limit: int = 0) -> list[RunRow]:
    """Return runs ordered by started_at DESC. limit=0 means no limit."""
    sql = f"SELECT {_LIST_COLS} FROM runs ORDER BY started_at DESC"
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_runrow(r) for r in db.execute(sql).fetchall()]


def get_run(db: sqlite3.Connection, job_id: str) -> RunRow | None:
    row = db.execute(
        f"SELECT {_LIST_COLS} FROM runs WHERE job_id = ?", (job_id,),
    ).fetchone()
    return _row_to_runrow(row) if row else None


def rebuild_index(
    db: sqlite3.Connection, evaluations_root: Path,
) -> tuple[int, int]:
    """Drop all rows, re-sync from filesystem. Returns (count, elapsed_ms)."""
    start = _time.monotonic()
    with db:
        db.execute("DELETE FROM runs")
    sync_index(db, evaluations_root)
    count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    elapsed_ms = int((_time.monotonic() - start) * 1000)
    return count, elapsed_ms


def delete_run(db: sqlite3.Connection, job_id: str) -> bool:
    """Remove a run from the index. Returns True if a row was deleted."""
    with db:
        cur = db.execute("DELETE FROM runs WHERE job_id = ?", (job_id,))
    return cur.rowcount > 0
