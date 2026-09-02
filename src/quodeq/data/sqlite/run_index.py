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

from quodeq.data.sqlite._index_sync import (
    _check_stale_and_promote,
    _delete_orphan_non_terminal_rows,
    _status_mtime_ns,
    _sync_legacy_run,
    _upsert_from_status,
)
from quodeq.data.sqlite._run_index_schema import (
    SCHEMA_VERSION,  # noqa: F401 — re-export
    open_index,  # noqa: F401 — re-export
)

_logger = logging.getLogger(__name__)


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


def _sync_status_backed_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtimes: dict[str, int] | None = None,
) -> None:
    """Sync a run that has a ``status.json`` (the common, non-legacy case)."""
    disk_mtime = _status_mtime_ns(run_dir)
    job_id = f"ext-{run_id}"
    if cached_mtimes is not None:
        cached_value = cached_mtimes.get(job_id)
    else:
        row = db.execute(
            "SELECT status_mtime FROM runs WHERE job_id = ?", (job_id,),
        ).fetchone()
        cached_value = row[0] if row is not None else None
    if cached_value is None or cached_value != disk_mtime:
        try:
            _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("skipping run %s: %s", run_dir, exc, exc_info=True)
            return
    # Always check staleness, even on mtime-unchanged runs.
    try:
        _check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)
    except Exception as exc:
        _logger.warning("stale-check failed for %s: %s", run_dir, exc, exc_info=True)


def _sync_one_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtimes: dict[str, int] | None = None,
) -> None:
    status_path = run_dir / "status.json"
    if status_path.exists():
        _sync_status_backed_run(
            db, run_dir, project_uuid=project_uuid, run_id=run_id,
            cached_mtimes=cached_mtimes,
        )
    else:
        try:
            _sync_legacy_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        except Exception as exc:
            _logger.warning("legacy sync failed for %s: %s", run_dir, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Public sync API
# ---------------------------------------------------------------------------

def sync_index(db: sqlite3.Connection, evaluations_root: Path) -> None:
    """Lazy upsert: walk *evaluations_root*, sync any run whose status.json
    changed since last seen OR that lacks an index row entirely. Promote
    stale non-terminal runs. Sweep non-terminal rows whose ``run_dir`` is
    gone — those can't be rescued by the heartbeat-based stale check.
    """
    with db:
        cached_mtimes = {
            job_id: status_mtime
            for job_id, status_mtime in db.execute("SELECT job_id, status_mtime FROM runs")
        }
        for project_uuid, run_id, run_dir in _walk_run_dirs(evaluations_root):
            _sync_one_run(
                db, run_dir, project_uuid=project_uuid, run_id=run_id,
                cached_mtimes=cached_mtimes,
            )
        _delete_orphan_non_terminal_rows(db)


def sync_index_for_run(db: sqlite3.Connection, run_dir: Path) -> None:
    """Sync only the given run_dir (used by /api/evaluations/<id>)."""
    if not run_dir.is_dir():
        return
    project_uuid = run_dir.parent.name
    run_id = run_dir.name
    with db:
        _sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def sync_project_dates(db: sqlite3.Connection, project_dir: Path, project_uuid: str) -> None:
    """Mtime-gated upsert of one project's runs' ``started_at`` into the index.

    Lighter than :func:`sync_index` / ``_sync_one_run``: refreshes only rows whose
    ``status.json`` mtime changed, and skips stale-promotion (the run date needs
    only the immutable ``started_at``). Runs without ``status.json`` are left to
    the caller's ``parse_run_date`` fallback. The mtime cache is keyed by
    ``(project_uuid, run_id)`` so it matches the row regardless of ``job_id``.
    """
    if not project_dir.is_dir():
        return
    with db:
        for run_dir in project_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            if not (run_dir / "status.json").exists():
                continue
            disk_mtime = _status_mtime_ns(run_dir)
            cached = db.execute(
                "SELECT status_mtime FROM runs WHERE project_uuid=? AND run_id=?",
                (project_uuid, run_dir.name),
            ).fetchone()
            if cached is None or cached[0] != disk_mtime:
                try:
                    _upsert_from_status(
                        db, run_dir, project_uuid=project_uuid, run_id=run_dir.name)
                except Exception:
                    _logger.warning("date-sync upsert failed for %s", run_dir, exc_info=True)


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


def list_runs_for_project(
    db: sqlite3.Connection, project_uuid: str, *, limit: int = 0,
) -> list[RunRow]:
    """Return one project's runs ordered by started_at DESC. limit=0 = no limit.

    Native indexed query — the replacement for walking the project's run dirs.
    """
    sql = (
        f"SELECT {_LIST_COLS} FROM runs WHERE project_uuid = ? "
        "ORDER BY started_at DESC"
    )
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_runrow(r) for r in db.execute(sql, (project_uuid,)).fetchall()]


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
