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
import re
import signal
import time
from pathlib import Path

from quodeq.analysis._process import _kill_tree
from quodeq.shared._env import env_float

_logger = logging.getLogger(__name__)

_PID_FILENAME = ".pid"

# Charset of a legitimate project/run directory name (UUIDs in practice).
# Excludes path separators; "." and ".." are rejected separately below.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9._-]+")

# Time to wait for the process to honor SIGTERM before escalating to SIGKILL.
# Long enough that graceful shutdown (per-dim scoring on cancel, status.json
# finalize, cache flush) finishes; short enough that the user isn't left
# waiting on a hung run. Overridable for ops via env var.
_DEFAULT_GRACE_PERIOD_S = env_float("QUODEQ_CANCEL_GRACE_S", 30.0, minimum=0.0)
_POLL_INTERVAL_S = 0.05
# SIGKILL on POSIX; Windows has no SIGKILL but _kill_tree treats any signal as
# "taskkill /F /T" -- the fallback to SIGTERM keeps the call valid.
_FORCE_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


def is_safe_run_segment(value: str) -> bool:
    """True when *value* is safe to use as a single path segment.

    Guards externally-supplied run/project ids (e.g. the tail of an
    ``ext-<run_id>`` job id from the API) before any filesystem path is
    built from them. Rejects empty strings, ``.``/``..`` and anything
    outside ``[A-Za-z0-9._-]``.
    """
    return bool(_SAFE_ID_RE.fullmatch(value)) and value not in (".", "..")


def resolve_external_pid(project_uuid: str, run_id: str, reports_root: Path) -> int | None:
    """Find the PID of the process running an external job, for cancellation.

    Looks for a `.pid` file written by `quodeq evaluate` at run start. Returns
    None if not found or the process is already gone.
    """
    if not is_safe_run_segment(project_uuid) or not is_safe_run_segment(run_id):
        return None
    pid_file = reports_root / project_uuid / run_id / _PID_FILENAME
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
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

    _kill_tree(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
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
        if not _is_pid_alive(pid):
            return True
        time.sleep(_POLL_INTERVAL_S)
    return not _is_pid_alive(pid)
