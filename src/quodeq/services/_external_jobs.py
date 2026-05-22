"""Cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``services/_index_sync.py`` (Plan B1).
Only the cancel path -- reading the ``.pid`` file and delivering signals --
remains here.

The cancel path is SIGTERM first, then SIGKILL after a grace window if the
process hasn't died. Both signals target the process *group* (the run's
session leader from ``start_new_session=True``) so subagent children get
reaped alongside the parent. Returning True means the process is now gone;
returning False means there was nothing to cancel or signal delivery failed.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

_PID_FILENAME = ".pid"

# Time to wait for the process to honor SIGTERM before escalating to SIGKILL.
# Long enough that graceful shutdown (per-dim scoring on cancel, status.json
# finalize, cache flush) finishes; short enough that the user isn't left
# waiting on a hung run. Overridable for ops via env var.
_DEFAULT_GRACE_PERIOD_S = float(os.environ.get("QUODEQ_CANCEL_GRACE_S", "30"))
_POLL_INTERVAL_S = 0.05


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
    # Use the shared liveness probe -- os.kill(pid, 0) is unsafe on
    # Windows (signal 0 == CTRL_C_EVENT, which can broadcast Ctrl+C
    # to the calling process). See _index_sync._is_pid_alive.
    from quodeq.services._index_sync import _is_pid_alive
    if not _is_pid_alive(pid):
        return None
    return pid


def cancel_external_run(
    project_uuid: str,
    run_id: str,
    reports_root: Path,
    *,
    grace_period_s: float | None = None,
) -> bool:
    """Stop an external run's process tree; escalate SIGTERM to SIGKILL after grace.

    Returns True once the process is gone (either honored SIGTERM or was
    killed). Returns False only when there was nothing to cancel or signal
    delivery failed at the OS level.
    """
    from quodeq.services._index_sync import _is_pid_alive

    grace = grace_period_s if grace_period_s is not None else _DEFAULT_GRACE_PERIOD_S
    pid = resolve_external_pid(project_uuid, run_id, reports_root)
    if pid is None:
        return False
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        return not _is_pid_alive(pid)

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError as exc:
        _logger.warning("Failed to SIGTERM pgid %s (pid %s): %s", pgid, pid, exc)
        return False

    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_S)

    _logger.warning(
        "SIGTERM grace window (%ss) expired for pid %s; escalating to SIGKILL",
        grace, pid,
    )
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError as exc:
        _logger.warning("Failed to SIGKILL pgid %s (pid %s): %s", pgid, pid, exc)
        return False
    # Brief wait so callers that immediately read status.json see a settled state.
    final_deadline = time.monotonic() + 1.0
    while time.monotonic() < final_deadline:
        if not _is_pid_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_S)
    return not _is_pid_alive(pid)
