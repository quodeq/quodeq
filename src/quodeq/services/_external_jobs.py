"""Cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``services/_index_sync.py`` (Plan B1).
Only the cancel path -- reading the ``.pid`` file and delivering signals --
remains here.

The cancel path is SIGTERM first, then SIGKILL after a grace window if the
process hasn't died. Tree kill is delegated to ``_kill_tree`` so subagent
children get reaped alongside the parent on both POSIX (``killpg``) and
Windows (``taskkill /T``). Returning True means the process is now gone;
returning False means there was nothing to cancel or signal delivery failed.
"""
from __future__ import annotations

import logging
import signal
import time
from pathlib import Path

from quodeq.analysis._process import _kill_tree
from quodeq.core.utils.io import resolve_child_dir
from quodeq.data.fs.report_parser._external_pid import (  # noqa: F401 — re-exported API
    is_safe_run_segment,
    resolve_external_pid,
)
from quodeq.shared._env import env_float
from quodeq.shared.process import is_pid_alive

_logger = logging.getLogger(__name__)

# Time to wait for the process to honor SIGTERM before escalating to SIGKILL.
# Long enough that graceful shutdown (per-dim scoring on cancel, status.json
# finalize, cache flush) finishes; short enough that the user isn't left
# waiting on a hung run. Overridable for ops via env var.
_DEFAULT_GRACE_PERIOD_S = env_float("QUODEQ_CANCEL_GRACE_S", 30.0, minimum=0.0)
_POLL_INTERVAL_S = 0.05
# SIGKILL on POSIX; Windows has no SIGKILL but _kill_tree treats any signal as
# "taskkill /F /T" -- the fallback to SIGTERM keeps the call valid.
_FORCE_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)




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
    grace = grace_period_s if grace_period_s is not None else _DEFAULT_GRACE_PERIOD_S
    project_dir = resolve_child_dir(reports_root, project_uuid)
    if project_dir is None:
        return False
    pid = resolve_external_pid(Path(project_dir), run_id)
    if pid is None:
        return False

    _kill_tree(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not is_pid_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_S)

    _logger.warning(
        "SIGTERM grace window (%ss) expired for pid %s; escalating to SIGKILL",
        grace, pid,
    )
    _kill_tree(pid, _FORCE_KILL_SIGNAL)
    # Brief wait so callers that immediately read status.json see a settled state.
    final_deadline = time.monotonic() + 1.0
    while time.monotonic() < final_deadline:
        if not is_pid_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_S)
    return not is_pid_alive(pid)
