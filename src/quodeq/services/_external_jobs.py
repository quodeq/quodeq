"""Cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``data/sqlite/index_sync.py`` (Plan B1).
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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.shared.process_kill import kill_tree as _kill_tree
from quodeq.core.utils.io import resolve_child_dir
from quodeq.core.run.job_status import strip_external_prefix
from quodeq.data.fs.report_parser.external_pid import (  # noqa: F401 — re-exported API
    is_safe_run_segment,
    resolve_external_pid,
)
from quodeq.services._run_index_fs import (
    _scan_reports_root_for_run, _sync_external_run_by_scan,
)
from quodeq.shared.env import env_float
from quodeq.shared.process import is_pid_alive
from quodeq.data.sqlite import run_index as _run_index

_logger = logging.getLogger(__name__)

# Time to wait for the process to honor SIGTERM before escalating to SIGKILL.
# Long enough that graceful shutdown (per-dim scoring on cancel, status.json
# finalize, cache flush) finishes; short enough that the user isn't left
# waiting on a hung run. Overridable for ops via env var.
_DEFAULT_GRACE_PERIOD_S = env_float("QUODEQ_CANCEL_GRACE_S", 30.0, minimum=0.0)
_POLL_INTERVAL_S = 0.05
# Settle window after SIGKILL, so a caller that reads status.json right
# after cancel sees a finished state rather than a half-written one.
_SETTLE_WAIT_S = 1.0
# SIGKILL on POSIX; Windows has no SIGKILL but _kill_tree treats any signal as
# "taskkill /F /T" -- the fallback to SIGTERM keeps the call valid.
_FORCE_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


@dataclass(frozen=True)
class ProcessControl:
    """Injectable seam for the process-control calls ``cancel_external_run`` makes."""

    kill_tree: Callable[[int, int], None] = _kill_tree
    pid_alive: Callable[[int], bool] = is_pid_alive


def _wait_for_exit(
    control: ProcessControl, pid: int, timeout: float, interval: float = _POLL_INTERVAL_S,
) -> bool:
    """Poll until *pid* is gone or *timeout* elapses. True if it exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not control.pid_alive(pid):
            return True
        time.sleep(interval)
    return False


def resolve_external_run_project(
    reports_root: Path, run_id: str, *, run_dir_hint: Path | None = None,
) -> str | None:
    """Return the project_uuid owning *run_id*, or None if not found.

    *run_dir_hint*, when it names a real directory, is trusted directly (its
    parent's name is the project_uuid) so a caller that already knows
    output_project/output_run_id skips scanning every project dir under
    *reports_root*.

    Without a hint this goes through ``_scan_reports_root_for_run``, the one
    copy of the scan, so the ``is_within`` jail applies here too.
    """
    if run_dir_hint is not None and run_dir_hint.is_dir():
        return run_dir_hint.parent.name
    candidate = _scan_reports_root_for_run(reports_root, run_id)
    return candidate.parent.name if candidate is not None else None


def cancel_external_run(
    project_uuid: str,
    run_id: str,
    reports_root: Path,
    *,
    grace_period_s: float | None = None,
    control: ProcessControl | None = None,
) -> bool:
    """Stop an external run's process tree; escalate SIGTERM to SIGKILL after grace.

    Returns True once the process is gone (either honored SIGTERM or was
    killed). Returns False only when there was nothing to cancel or signal
    delivery failed at the OS level.
    """
    grace = grace_period_s if grace_period_s is not None else _DEFAULT_GRACE_PERIOD_S
    control = control or ProcessControl()
    project_dir = resolve_child_dir(reports_root, project_uuid)
    if project_dir is None:
        return False
    pid = resolve_external_pid(Path(project_dir), run_id)
    if pid is None:
        return False

    control.kill_tree(pid, signal.SIGTERM)
    if _wait_for_exit(control, pid, grace):
        return True

    _logger.warning(
        "SIGTERM grace window (%ss) expired for pid %s; escalating to SIGKILL",
        grace, pid,
    )
    control.kill_tree(pid, _FORCE_KILL_SIGNAL)
    # Brief wait so callers that immediately read status.json see a settled state.
    if _wait_for_exit(control, pid, _SETTLE_WAIT_S):
        return True
    return not control.pid_alive(pid)


def _sync_external_run(db, job_id: str, reports_dir: Path) -> bool:
    """Bring the index row for an external run up to date; False if the id is unsafe.

    Prefers the run directory the index already knows. A blank run_dir falls
    through to the scan: ``Path("")`` is ``Path(".")``, whose ``is_dir()`` is
    True, so it would sync the process cwd as if it were the run.
    """
    run_id = strip_external_prefix(job_id)
    if not is_safe_run_segment(run_id):
        return False
    known = _run_index.get_run(db, job_id)
    run_dir = Path(known.run_dir) if known is not None and known.run_dir else None
    if run_dir is not None and run_dir.is_dir():
        _run_index.sync_index_for_run(db, run_dir)
    else:
        _sync_external_run_by_scan(db, reports_dir, run_id)
    return True
