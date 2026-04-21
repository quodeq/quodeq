"""SIGTERM cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``services/_index_sync.py`` (Plan B1).
Only the cancel path — reading the ``.pid`` file and delivering SIGTERM —
remains here.
"""
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

_logger = logging.getLogger(__name__)

_PID_FILENAME = ".pid"


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
