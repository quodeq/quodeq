# src/quodeq/services/run_index.py
"""SQLite-backed run index.

The index is **derived state** — rebuildable at any time from the filesystem
(``~/.quodeq/evaluations/**/status.json`` and legacy signals). Delete
``~/.quodeq/index.db`` at any time; the next ``open_index`` creates an empty
database and the next ``sync_index`` call repopulates.

Public API is the only stable surface — internals live in ``index_sync``.
"""
from __future__ import annotations

import logging
import sqlite3
import time as _time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from quodeq.data.sqlite.index_sync import delete_orphan_non_terminal_rows
from quodeq.data.sqlite._run_index_schema import (
    SCHEMA_VERSION,  # noqa: F401 — re-export
    open_index,  # noqa: F401 — re-export
)
from quodeq.data.sqlite._run_sync_step import (
    run_under_savepoint,
    sync_one_run,
    sync_one_run_isolated,
    upsert_if_changed,
)
from quodeq.shared.fault_isolation import run_isolated

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

def _visible_subdirs(directory: Path) -> Iterator[Path]:
    """Yield the subdirectories of *directory* whose names do not start with a dot."""
    for child in directory.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            yield child


def _walk_run_dirs(evaluations_root: Path):
    """Yield (project_uuid, run_id, run_dir) for every run on disk."""
    if not evaluations_root.is_dir():
        return
    for project_dir in _visible_subdirs(evaluations_root):
        for run_dir in _visible_subdirs(project_dir):
            yield project_dir.name, run_dir.name, run_dir


# ---------------------------------------------------------------------------
# Public sync API
# ---------------------------------------------------------------------------

def sync_index(db: sqlite3.Connection, evaluations_root: Path) -> None:
    """Lazy upsert: walk *evaluations_root*, sync any run whose status.json
    changed since last seen OR that lacks an index row entirely. Promote
    stale non-terminal runs. Sweep non-terminal rows whose ``run_dir`` is
    gone — those can't be rescued by the heartbeat-based stale check.

    Every run is one work-queue iteration under ``run_isolated``: one
    malformed run must not stop syncing the rest, or roll back the rows
    already synced earlier in this same call (the whole walk shares one
    ``with db:`` transaction).
    """
    with db:
        cached_mtimes = {
            job_id: status_mtime
            for job_id, status_mtime in db.execute("SELECT job_id, status_mtime FROM runs")
        }
        for project_uuid, run_id, run_dir in _walk_run_dirs(evaluations_root):
            run_isolated(
                lambda: sync_one_run_isolated(
                    db, run_dir, project_uuid=project_uuid, run_id=run_id,
                    cached_mtimes=cached_mtimes,
                ),
                label=f"index sync {run_id}",
                log=_logger,
            )
        delete_orphan_non_terminal_rows(db)


def sync_index_for_run(db: sqlite3.Connection, run_dir: Path) -> None:
    """Sync only the given run_dir (used by /api/evaluations/<id>)."""
    if not run_dir.is_dir():
        return
    project_uuid = run_dir.parent.name
    run_id = run_dir.name
    with db:
        sync_one_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def sync_project_dates(db: sqlite3.Connection, project_dir: Path, project_uuid: str) -> None:
    """Mtime-gated upsert of one project's runs' ``started_at`` into the index.

    Lighter than :func:`sync_index` / ``sync_one_run``: refreshes only rows whose
    ``status.json`` mtime changed, and skips stale-promotion (the run date needs
    only the immutable ``started_at``). Runs without ``status.json`` are left to
    the caller's ``parse_run_date`` fallback. The mtime cache is prefetched for
    the whole project in one query (mirrors :func:`sync_index`'s ``cached_mtimes``
    at module scope), keyed by ``run_id`` since ``project_uuid`` is fixed here.

    Every run is one work-queue iteration under ``run_isolated``, same as
    :func:`sync_index`: one malformed run must not stop syncing the rest.
    """
    if not project_dir.is_dir():
        return
    with db:
        cached_mtimes = {
            run_id: status_mtime
            for run_id, status_mtime in db.execute(
                "SELECT run_id, status_mtime FROM runs WHERE project_uuid=?",
                (project_uuid,),
            )
        }
        for run_dir in _visible_subdirs(project_dir):
            if not (run_dir / "status.json").exists():
                continue
            run_isolated(
                lambda: run_under_savepoint(
                    db, lambda: upsert_if_changed(
                        db, run_dir, project_uuid=project_uuid, run_id=run_dir.name,
                        cached_mtime=cached_mtimes.get(run_dir.name),
                    ),
                ),
                label=f"index sync {run_dir.name}",
                log=_logger,
            )


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

_LIST_COLS = (
    "job_id, project_uuid, run_id, run_dir, state, phase, current_dimension, "
    "started_at, updated_at, finalized_at, heartbeat_at, pid, exit_reason, status_mtime"
)


def _row_to_runrow(row: tuple) -> RunRow:
    return RunRow(*row)


def _limit_clause(limit: int | None) -> str:
    """``LIMIT n`` for a positive *limit*, nothing for None; anything else is a caller bug."""
    if limit is None:
        return ""
    if limit <= 0:
        raise ValueError(f"limit must be positive or None, got {limit!r}")
    return f" LIMIT {int(limit)}"


def list_runs(
    db: sqlite3.Connection, *, limit: int | None, states: Iterable[str] | None = None,
) -> list[RunRow]:
    """Return runs ordered by started_at DESC.

    *limit* None returns every row; an int must be positive. *states*, when
    given, narrows the query in SQL instead of fetching every row to filter
    in Python.
    """
    where, params = "", ()
    if states:
        wanted = tuple(states)
        where = " WHERE state IN (" + ",".join("?" * len(wanted)) + ")"
        params = wanted
    sql = f"SELECT {_LIST_COLS} FROM runs{where} ORDER BY started_at DESC{_limit_clause(limit)}"
    return [_row_to_runrow(r) for r in db.execute(sql, params).fetchall()]


def list_runs_for_project(
    db: sqlite3.Connection, project_uuid: str, *, limit: int | None,
) -> list[RunRow]:
    """Return one project's runs ordered by started_at DESC.

    *limit* None returns every row; an int must be positive. Native indexed
    query — the replacement for walking the project's run dirs.
    """
    sql = (
        f"SELECT {_LIST_COLS} FROM runs WHERE project_uuid = ? "
        f"ORDER BY started_at DESC{_limit_clause(limit)}"
    )
    return [_row_to_runrow(r) for r in db.execute(sql, (project_uuid,)).fetchall()]


def get_run(db: sqlite3.Connection, job_id: str) -> RunRow | None:
    """Return the indexed row for *job_id*, or None when the index has no such run.

    A miss means the index is stale, not that the run is gone — the caller
    falls back to the filesystem.
    """
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
