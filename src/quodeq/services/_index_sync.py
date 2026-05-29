"""Internal sync logic for the SQLite run index.

Upserts rows from status.json (Plan A runs) or synthesizes from legacy
filesystem signals (pre-Plan-A runs). Promotes stale non-terminal runs to
cancelled based on heartbeat mtime + PID liveness.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
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
    """Return True if *pid* refers to a live process. POSIX + Windows.

    On POSIX, ``os.kill(pid, 0)`` is the canonical no-op probe.

    On Windows, ``os.kill(pid, 0)`` is *not* a probe — signal 0 is
    ``CTRL_C_EVENT``, and Python implements that via
    ``GenerateConsoleCtrlEvent(CTRL_C_EVENT, pid)``. For an invalid /
    non-existent pid the Win32 call can broadcast Ctrl+C to every
    process sharing the calling console, which on test runners means
    pytest itself receives KeyboardInterrupt mid-run. Use
    ``OpenProcess`` + ``GetExitCodeProcess`` instead, which are
    side-effect-free and tolerate dead PIDs cleanly.
    """
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid),
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
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


def _delete_orphan_non_terminal_rows(db: sqlite3.Connection) -> int:
    """Remove non-terminal rows whose ``run_dir`` no longer exists on disk.

    Without this sweep, an orphan row (e.g. left by a crashed test, a manually
    deleted run dir, or a partial cleanup) stays as ``running`` forever:
    ``_check_stale_and_promote`` reads ``.heartbeat`` from ``run_dir``, and an
    unreadable heartbeat (no dir) provides no liveness signal, so the row is
    never promoted. Terminal rows are left alone — users may prune old dirs
    to save disk and the index is their only record.
    """
    placeholders = ", ".join("?" for _ in _TERMINAL_STATE_VALUES)
    rows = db.execute(
        f"SELECT job_id, run_dir FROM runs WHERE state NOT IN ({placeholders})",
        tuple(_TERMINAL_STATE_VALUES),
    ).fetchall()
    orphan_ids = [job_id for job_id, run_dir in rows if not Path(run_dir).is_dir()]
    if not orphan_ids:
        return 0
    db.executemany("DELETE FROM runs WHERE job_id = ?", [(j,) for j in orphan_ids])
    return len(orphan_ids)


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
    row = db.execute(
        "SELECT state, project_uuid, run_id, started_at, phase, "
        "current_dimension, pid FROM runs WHERE job_id = ?", (job_id,),
    ).fetchone()
    if row is None:
        return False
    state, project_uuid, run_id, started_at, phase, current_dimension, pid = row
    if state in _TERMINAL_STATE_VALUES:
        return False

    # Prefer the FS path: write status.json and let the upsert sync the row.
    if run_dir is not None and run_dir.is_dir():
        try:
            existing = read_status(run_dir) or {}
            dimensions = existing.get("dimensions") or []
            write_status(
                run_dir,
                state=RunState.CANCELLED,
                job_id=job_id,
                started_at=started_at or existing.get("started_at", ""),
                dimensions=dimensions,
                phase=phase,
                current_dimension=current_dimension,
                pid=pid if isinstance(pid, int) else None,
                exit_reason="stale_detected",
            )
            _upsert_from_status(
                db, run_dir, project_uuid=project_uuid, run_id=run_id,
            )
            return True
        except (OSError, UnsupportedSchemaError) as exc:
            _logger.warning(
                "force-promote: status.json write failed for %s (%s); "
                "falling back to index-only update", job_id, exc,
            )
            # Fall through to DB-only path.

    # No run_dir on disk (full orphan): update the index row directly.
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.execute(
        "UPDATE runs SET state = ?, exit_reason = ?, finalized_at = ?, "
        "updated_at = ? WHERE job_id = ?",
        ("cancelled", "stale_detected", now_iso, now_iso, job_id),
    )
    return True


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
            # Preserve deadline_at across the stale → cancelled rewrite so
            # downstream readers (filesystem snapshot builder) still see it.
            deadline_at=status.get("deadline_at"),
            # Preserve provider/model so the dashboard card stays self-describing.
            ai_provider=status.get("ai_provider"),
            ai_model=status.get("ai_model"),
        )
        with db:
            _upsert_from_status(db, run_dir, project_uuid=project_uuid, run_id=run_id)
        return True

    return False
