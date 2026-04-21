"""Internal sync logic for the SQLite run index.

Upserts rows from status.json (Plan A runs) or synthesizes from legacy
filesystem signals (pre-Plan-A runs). Promotes stale non-terminal runs to
cancelled based on heartbeat mtime + PID liveness.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from quodeq.shared.run_heartbeat import HEARTBEAT_FILENAME
from quodeq.shared.run_status import (
    RunState,
    STATUS_FILENAME,
    TERMINAL_STATES,
    UnsupportedSchemaError,
    read_status,
    write_status,
)

_logger = logging.getLogger(__name__)

_TERMINAL_STATE_VALUES = {s.value for s in TERMINAL_STATES}

_UPSERT_SQL = """
INSERT INTO runs (
    job_id, project_uuid, run_id, run_dir, state, phase, current_dimension,
    started_at, updated_at, finalized_at, heartbeat_at, pid, exit_reason, status_mtime
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(job_id) DO UPDATE SET
    project_uuid=excluded.project_uuid,
    run_id=excluded.run_id,
    run_dir=excluded.run_dir,
    state=excluded.state,
    phase=excluded.phase,
    current_dimension=excluded.current_dimension,
    started_at=excluded.started_at,
    updated_at=excluded.updated_at,
    finalized_at=excluded.finalized_at,
    heartbeat_at=excluded.heartbeat_at,
    pid=excluded.pid,
    exit_reason=excluded.exit_reason,
    status_mtime=excluded.status_mtime
"""


def _is_pid_alive(pid: int) -> bool:
    """Return True if *pid* refers to a live process. POSIX + Windows."""
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _heartbeat_mtime(run_dir: Path) -> float | None:
    path = run_dir / HEARTBEAT_FILENAME
    try:
        return path.stat().st_mtime
    except (OSError, FileNotFoundError):
        return None


def _heartbeat_iso(run_dir: Path) -> str | None:
    m = _heartbeat_mtime(run_dir)
    if m is None:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(m, tz=timezone.utc).isoformat(timespec="seconds")


def _status_mtime_ns(run_dir: Path) -> int:
    try:
        return (run_dir / STATUS_FILENAME).stat().st_mtime_ns
    except (OSError, FileNotFoundError):
        return 0


def _upsert_from_status(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    """Read status.json + heartbeat, upsert the row."""
    try:
        status = read_status(run_dir)
    except UnsupportedSchemaError:
        _logger.warning("skipping run %s: status schema newer than supported", run_dir)
        return
    if status is None:
        return
    job_id = status.get("job_id") or f"ext-{run_id}"
    with db:
        db.execute(
            _UPSERT_SQL,
            (
                job_id,
                project_uuid,
                run_id,
                str(run_dir),
                status.get("state", "running"),
                status.get("phase"),
                status.get("current_dimension"),
                status.get("started_at", ""),
                status.get("updated_at", ""),
                status.get("finalized_at"),
                _heartbeat_iso(run_dir),
                status.get("pid"),
                status.get("exit_reason"),
                _status_mtime_ns(run_dir),
            ),
        )


def _sync_legacy_run(
    db: sqlite3.Connection, run_dir: Path, *, project_uuid: str, run_id: str,
) -> None:
    """Synthesize a row from filesystem signals for pre-Plan-A runs (no status.json)."""
    scan_path = run_dir / "scan.json"
    pid_path = run_dir / ".pid"
    manifest_path = run_dir / "evidence" / "manifest.json"
    if not manifest_path.exists():
        return  # not a real run

    state: str
    exit_reason: str | None

    if scan_path.exists():
        state, exit_reason = "done", None
    elif pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            alive = _is_pid_alive(pid)
        except (OSError, ValueError):
            alive = False
        if alive:
            state, exit_reason = "running", None
        else:
            state, exit_reason = "cancelled", "stale_legacy_pid_dead"
    else:
        state, exit_reason = "cancelled", "stale_legacy_no_pid"

    job_id = f"ext-{run_id}"
    try:
        started_ts = manifest_path.stat().st_mtime
    except OSError:
        started_ts = time.time()
    from datetime import datetime, timezone
    started_iso = datetime.fromtimestamp(started_ts, tz=timezone.utc).isoformat(timespec="seconds")

    with db:
        db.execute(
            _UPSERT_SQL,
            (
                job_id, project_uuid, run_id, str(run_dir),
                state, None, None,
                started_iso, started_iso, started_iso if state in _TERMINAL_STATE_VALUES else None,
                None, None, exit_reason,
                0,
            ),
        )


def _check_stale_and_promote(
    db: sqlite3.Connection, run_dir: Path, *,
    project_uuid: str, run_id: str, stale_seconds: int = 30,
) -> bool:
    """Promote non-terminal runs with dead heartbeat + dead PID to cancelled.

    Returns True if a promotion occurred. Writes status.json back to disk
    (via run_status.write_status) so the terminal state is durable across
    dashboard sessions.
    """
    try:
        status = read_status(run_dir)
    except UnsupportedSchemaError:
        return False
    if status is None:
        return False
    state = status.get("state")
    if state in _TERMINAL_STATE_VALUES:
        return False

    heartbeat_mtime = _heartbeat_mtime(run_dir)
    heartbeat_stale = heartbeat_mtime is None or (time.time() - heartbeat_mtime) > stale_seconds

    pid = status.get("pid")
    pid_alive = isinstance(pid, int) and _is_pid_alive(pid)

    if heartbeat_stale and not pid_alive:
        write_status(
            run_dir,
            state=RunState.CANCELLED,
            job_id=status.get("job_id", f"ext-{run_id}"),
            started_at=status.get("started_at", ""),
            dimensions=status.get("dimensions") or [],
            phase=status.get("phase"),
            current_dimension=status.get("current_dimension"),
            pid=pid if isinstance(pid, int) else None,
            exit_reason="stale_detected",
        )
        _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        return True

    return False
