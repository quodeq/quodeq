"""One run's sync step, plus the fault isolation run_index's batch loops need.

``run_index.py`` owns the loops (``sync_index``, ``sync_project_dates``) that
call ``sync_one_run_isolated``/``run_under_savepoint`` once per run, and
``sync_index_for_run`` for the single-run API path (already inside its own
dedicated ``with db:``, so no extra isolation is needed there).

Names here have no leading underscore even though this module is a private
sibling of ``run_index.py``: ``tools/check_private_imports.py``'s strict
src rule (rule 2) forbids importing a `_name` across files, same directory
or not (mirrors the existing ``index_sync.py`` convention -- its functions
are plain names for the same reason).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from quodeq.core.run.job_status import external_job_id
from quodeq.data.sqlite.index_sync import (
    check_stale_and_promote,
    status_mtime_ns,
    sync_legacy_run,
    upsert_from_status,
)


def upsert_if_changed(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtime: int | None,
) -> None:
    """Upsert the run's row from ``status.json`` unless *cached_mtime* still matches it.

    Raises whatever ``upsert_from_status`` raises; each caller owns its policy.
    """
    if cached_mtime is None or cached_mtime != status_mtime_ns(run_dir):
        upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def _sync_status_backed_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtimes: dict[str, int | None] | None = None,
) -> None:
    """Sync a run that has a ``status.json`` (the common, non-legacy case).

    Raises whatever the upsert or stale-check raises. This is deliberate:
    the caller is the per-run fault-isolation boundary (see
    :func:`sync_one_run_isolated`), which decides what a failure here
    means for the rest of the batch. Narrowing the exception type here
    would only rename the same "abort this run" outcome.
    """
    job_id = external_job_id(run_id)
    if cached_mtimes is not None:
        cached_value = cached_mtimes.get(job_id)
    else:
        row = db.execute(
            "SELECT status_mtime FROM runs WHERE job_id = ?", (job_id,),
        ).fetchone()
        cached_value = row[0] if row is not None else None
    upsert_if_changed(db, run_dir, project_uuid=project_uuid, run_id=run_id, cached_mtime=cached_value)
    # Always check staleness, even on mtime-unchanged runs.
    check_stale_and_promote(db, run_dir, project_uuid=project_uuid, run_id=run_id)


def sync_one_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtimes: dict[str, int | None] | None = None,
) -> None:
    """Sync one run's row. Raises whatever the status-backed or legacy sync
    path raises -- see :func:`_sync_status_backed_run`."""
    status_path = run_dir / "status.json"
    if status_path.exists():
        _sync_status_backed_run(
            db, run_dir, project_uuid=project_uuid, run_id=run_id,
            cached_mtimes=cached_mtimes,
        )
    else:
        sync_legacy_run(db, run_dir, project_uuid=project_uuid, run_id=run_id)


_SYNC_SAVEPOINT = "sync_one_run"


def run_under_savepoint(db: sqlite3.Connection, fn: Callable[[], None]) -> None:
    """Run *fn* so its writes are all-or-nothing: a failure rolls back only
    *fn*'s own writes, leaving rows already released by earlier calls (or
    committed by a nested ``with db:`` inside *fn*, e.g. stale promotion)
    untouched.

    ``db.in_transaction`` is checked before RELEASE/ROLLBACK TO: a nested
    ``with db:`` that already committed also releases every savepoint as a
    side effect, so there is nothing left to release or roll back to.
    """
    db.execute(f"SAVEPOINT {_SYNC_SAVEPOINT}")
    try:
        fn()
    except Exception:
        if db.in_transaction:
            db.execute(f"ROLLBACK TO {_SYNC_SAVEPOINT}")
            db.execute(f"RELEASE {_SYNC_SAVEPOINT}")
        raise
    else:
        if db.in_transaction:
            db.execute(f"RELEASE {_SYNC_SAVEPOINT}")


def sync_one_run_isolated(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
    cached_mtimes: dict[str, int | None] | None,
) -> None:
    """One run is one work-queue iteration: sync it under its own SAVEPOINT
    so a failure never leaves a partial row, then let the caller's
    ``run_isolated`` decide the batch's fate -- one malformed run must not
    stop syncing the rest."""
    run_under_savepoint(
        db, lambda: sync_one_run(
            db, run_dir, project_uuid=project_uuid, run_id=run_id, cached_mtimes=cached_mtimes,
        ),
    )
