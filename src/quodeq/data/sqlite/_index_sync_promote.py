"""Force-promote-to-cancelled helpers for the SQLite run index.

Split out of ``_index_sync.py`` purely to keep that module under the size
cap (an intra-file extraction there would have pushed it over 300 lines).
``force_promote_to_cancelled_stale`` is re-exported from ``_index_sync`` --
that is the stable entry point callers use. The few names shared with
``_index_sync`` (``_logger``, ``_TERMINAL_STATE_VALUES``,
``_upsert_from_status``) are looked up via a deferred import inside each
function body, so this module carries no top-level dependency back on
``_index_sync`` and there is no import cycle.
"""
from __future__ import annotations

import dataclasses
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from quodeq.data.fs.run_status_store import (
    RunState,
    RunStatus,
    UnsupportedSchemaError,
    read_status,
    write_status,
)


class _StaleRunRow(NamedTuple):
    """One row of the ``runs`` table, in SELECT column order."""

    state: str
    project_uuid: str
    run_id: str
    started_at: str | None
    phase: str | None
    current_dimension: str | None
    pid: int | None


def _promote_via_status_write(
    db: sqlite3.Connection, job_id: str, run_dir: Path, row: _StaleRunRow,
) -> bool:
    """Rewrite status.json to cancelled and let the upsert sync the row.

    Returns True on success. On a write failure, logs and returns False so
    the caller can fall back to the DB-only path.
    """
    from quodeq.data.sqlite._index_sync import _logger, _upsert_from_status

    try:
        existing = read_status(run_dir) or {}
        existing.setdefault("state", row.state)
        base = RunStatus.from_status_dict(existing)
        status = dataclasses.replace(
            base,
            state=RunState.CANCELLED,
            job_id=job_id,
            started_at=row.started_at or base.started_at,
            phase=row.phase,
            current_dimension=row.current_dimension,
            pid=row.pid if isinstance(row.pid, int) else None,
            exit_reason="stale_detected",
            finalized_at=None,
            time_limit_s=None,
        )
        write_status(run_dir, status)
        _upsert_from_status(
            db, run_dir, project_uuid=row.project_uuid, run_id=row.run_id,
        )
        return True
    except (OSError, UnsupportedSchemaError) as exc:
        _logger.warning(
            "force-promote: status.json write failed for %s (%s); "
            "falling back to index-only update", job_id, exc,
        )
        return False


def _promote_index_only(db: sqlite3.Connection, job_id: str) -> None:
    """Update the index row directly (no run_dir on disk / full orphan)."""
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.execute(
        "UPDATE runs SET state = ?, exit_reason = ?, finalized_at = ?, "
        "updated_at = ? WHERE job_id = ?",
        ("cancelled", "stale_detected", now_iso, now_iso, job_id),
    )


def force_promote_to_cancelled_stale(
    db: sqlite3.Connection, job_id: str, *, run_dir: Path | None = None,
) -> bool:
    """Mark a non-terminal index row as ``cancelled(stale_detected)``.

    Called from the cancel path when SIGTERM has nothing to signal (PID is
    dead). The row stays in the index — history is preserved. State flips
    to terminal so the dashboard no longer treats the job as live.

    If *run_dir* is provided and exists, ``status.json`` is also rewritten
    so the on-disk source of truth matches the index. Findings inside
    ``run_dir`` are not touched.

    Returns True if the row was promoted, False if it didn't exist or was
    already terminal.
    """
    from quodeq.data.sqlite._index_sync import _TERMINAL_STATE_VALUES

    row = db.execute(
        "SELECT state, project_uuid, run_id, started_at, phase, "
        "current_dimension, pid FROM runs WHERE job_id = ?", (job_id,),
    ).fetchone()
    if row is None:
        return False
    stale_row = _StaleRunRow(*row)
    if stale_row.state in _TERMINAL_STATE_VALUES:
        return False

    # Prefer the FS path: write status.json and let the upsert sync the row.
    if run_dir is not None and run_dir.is_dir():
        if _promote_via_status_write(db, job_id, run_dir, stale_row):
            return True
        # Fall through to DB-only path.

    # No run_dir on disk (full orphan): update the index row directly.
    _promote_index_only(db, job_id)
    return True
