"""Detect externally-launched evaluations by scanning the filesystem.

External jobs are evaluations spawned outside the dashboard UI (CI runners,
`quodeq evaluate` in another terminal). They write the same filesystem
artifacts as UI-launched jobs but do not register with JobManager.

This module reconstructs JobSnapshot objects from those artifacts so they
can be surfaced in the Evaluation tab with live progress.
"""
from __future__ import annotations

import json
import logging
import os
import signal
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.types.job import JobSnapshot

_logger = logging.getLogger(__name__)

_EXTERNAL_JOB_ID_PREFIX = "ext-"
_PID_FILENAME = ".pid"
_MANIFEST_PATH = "evidence/manifest.json"
_SCAN_FILENAME = "scan.json"


def _is_pid_alive(pid: int) -> bool:
    """Return True if *pid* corresponds to a live process.

    Uses ``os.kill(pid, 0)``: signal 0 is a no-op that still raises OSError
    if the process does not exist. Works on both POSIX and Windows.
    """
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _pid_liveness(run_dir: Path) -> bool:
    """Return True if the run appears genuinely in-progress (.pid exists + PID is alive)."""
    pid_path = run_dir / _PID_FILENAME
    if not pid_path.exists():
        return False  # no evidence of liveness -> treat as stale
    try:
        pid = int(pid_path.read_text().strip())
    except (OSError, ValueError):
        return False
    return _is_pid_alive(pid)


def find_external_runs(reports_root: Path) -> list[JobSnapshot]:
    """Scan all projects for in-progress runs not tracked by any JobStore.

    Returns JobSnapshots in 'running' status with inferred phase/dimension.
    Caller is responsible for de-duplicating against JobManager-tracked jobs.
    """
    if not reports_root.is_dir():
        return []
    snapshots: list[JobSnapshot] = []
    # Two-level: reports_root / {project_uuid} / {run_id} /
    for project_dir in reports_root.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        for run_dir in project_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            snapshot = _run_dir_to_snapshot(project_dir.name, run_dir)
            if snapshot is not None:
                snapshots.append(snapshot)
    return snapshots


def _run_dir_to_snapshot(project_uuid: str, run_dir: Path) -> JobSnapshot | None:
    """Convert a run directory to a JobSnapshot.

    Returns:
        - ``None`` if the directory isn't an evaluation run.
        - A snapshot with ``status="running"`` if the .pid file points at a live process.
        - A snapshot with ``status="cancelled"`` if the run appears stale
          (scan.json absent AND no live PID -- force-exit, crash, or abnormal shutdown).
    """
    manifest_path = run_dir / _MANIFEST_PATH
    scan_path = run_dir / _SCAN_FILENAME

    if not manifest_path.exists():
        return None  # not a real run
    if scan_path.exists():
        return None  # run is complete, not external-in-progress

    # Infer phase, current dimension, dimensions list
    eval_dir = run_dir / "evaluation"
    evidence_dir = run_dir / "evidence"
    dimensions, current_dimension, phase = _infer_progress(eval_dir, evidence_dir)

    # Liveness check: alive PID -> running; missing/stale PID -> cancelled (stale).
    status = "running" if _pid_liveness(run_dir) else "cancelled"

    # External job_id is prefixed so the frontend/backend can distinguish it
    job_id = f"{_EXTERNAL_JOB_ID_PREFIX}{run_dir.name}"
    started_at_iso = _manifest_started_at(manifest_path)

    return JobSnapshot(
        job_id=job_id,
        status=status,
        phase=phase,
        current_dimension=current_dimension,
        dimensions=dimensions if dimensions else None,
        output_project=project_uuid,
        output_run_id=run_dir.name,
        started_at=started_at_iso,
        ended_at=None,
        exit_code=None,
        logs=[],  # no live log stream for externals; frontend shows filesystem state
        source="external",
    )


def _infer_progress(eval_dir: Path, evidence_dir: Path) -> tuple[list[str], str | None, str]:
    """From filesystem state, infer dimensions list, current_dimension, and phase."""
    # Completed dimensions: every {dim}.json in evaluation/ (not _full.json)
    completed: list[str] = []
    if eval_dir.is_dir():
        for f in sorted(eval_dir.iterdir()):
            if f.is_file() and f.suffix == ".json" and not f.stem.endswith("_full"):
                completed.append(f.stem)

    # In-progress dimensions: evidence/{dim}_evidence.jsonl present but no {dim}.json
    in_progress_dims: list[str] = []
    if evidence_dir.is_dir():
        for f in evidence_dir.iterdir():
            if f.name.endswith("_evidence.jsonl"):
                dim = f.name[: -len("_evidence.jsonl")]
                if dim not in completed:
                    in_progress_dims.append(dim)

    dimensions = completed + in_progress_dims

    # Current dimension: the most-recently-modified in-progress evidence file
    current: str | None = None
    if in_progress_dims and evidence_dir.is_dir():
        candidates = [(evidence_dir / f"{d}_evidence.jsonl", d) for d in in_progress_dims]
        candidates = [(p, d) for p, d in candidates if p.exists()]
        if candidates:
            candidates.sort(key=lambda pd: pd[0].stat().st_mtime, reverse=True)
            current = candidates[0][1]

    # Phase inference
    if not completed and not in_progress_dims:
        phase = "setup"
    elif in_progress_dims:
        phase = "analyzing"
    else:
        phase = "scoring"

    return dimensions, current, phase


def _manifest_started_at(manifest_path: Path) -> str:
    """Use manifest.json mtime as started_at (ISO 8601)."""
    ts = manifest_path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def resolve_external_pid(project_uuid: str, run_id: str, reports_root: Path) -> int | None:
    """Find the PID of the process running an external job, for cancellation.

    Looks for a `.pid` file written by `quodeq evaluate` at run start. Returns
    None if not found or the process is already gone.
    """
    pid_file = reports_root / project_uuid / run_id / _PID_FILENAME
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None
    # Verify the process exists
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def cancel_external_run(project_uuid: str, run_id: str, reports_root: Path) -> bool:
    """Send SIGTERM to the external run's process. Returns True if signal sent."""
    pid = resolve_external_pid(project_uuid, run_id, reports_root)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError as exc:
        _logger.warning("Failed to signal pid %s: %s", pid, exc)
        return False
