"""Cancel path for external (CLI-started) evaluations.

Dashboard-side detection and status inference for external runs now
lives in ``services/run_index.py`` and ``data/sqlite/index_sync.py``.
Only the cancel path -- reading the ``.pid`` file and delivering signals --
remains here.

The cancel path is SIGTERM first, then SIGKILL after a grace window if the
process hasn't died. Tree kill is delegated to ``kill_external_tree`` so subagent
children get reaped alongside the parent (``taskkill /T`` on Windows) without
signalling the launcher's process group: a CI step shares the self-hosted
runner's group, and a group kill would stop the runner. By default only the SIGTERM is delivered on the
caller's thread; the grace wait and SIGKILL escalation run on a daemon
thread so a cancel request never holds an HTTP worker for the grace window.
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import sqlite3

from quodeq.config.services_env import cancel_grace_s
from quodeq.shared.process_kill import kill_external_tree
from quodeq.core.utils.io import resolve_child_dir
from quodeq.core.run.job_status import strip_external_prefix
from quodeq.services._run_index_fs import (
    scan_reports_root_for_run, sync_external_run_by_scan,
)
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.process import is_pid_alive
from quodeq.services.wiring import (
    is_safe_run_segment,
    resolve_external_pid,
    run_index as _run_index,
)

_logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 0.05
# Settle window after SIGKILL, so a caller that reads status.json right
# after cancel sees a finished state rather than a half-written one.
_SETTLE_WAIT_S = 1.0
# SIGKILL on POSIX; Windows has no SIGKILL but kill_external_tree treats any signal as
# "taskkill /F /T" -- the fallback to SIGTERM keeps the call valid.
_FORCE_KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)
_ESCALATION_THREAD_NAME = "cancel-escalation-"


def _start_daemon(fn: Callable[[], None], name: str) -> None:
    """Run *fn* on its own daemon thread.

    Not the shared ``BackgroundRunner``: that pool may drop a task when its
    queue is full, and a dropped escalation would leave a SIGTERM-ignoring
    run alive. A cancel is rare and user-initiated, so one thread each is fine.
    """
    threading.Thread(target=fn, name=name, daemon=True).start()


@dataclass(frozen=True)
class ProcessControl:
    """Injectable seam for the process-control calls ``cancel_external_run`` makes."""

    kill_tree: Callable[[int, int], None] = kill_external_tree
    pid_alive: Callable[[int], bool] = is_pid_alive
    start_background: Callable[[Callable[[], None], str], None] = _start_daemon


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

    Without a hint this goes through ``scan_reports_root_for_run``, the one
    copy of the scan, so the ``is_within`` jail applies here too.
    """
    if run_dir_hint is not None and run_dir_hint.is_dir():
        return run_dir_hint.parent.name
    candidate = scan_reports_root_for_run(reports_root, run_id)
    return candidate.parent.name if candidate is not None else None


@dataclass(frozen=True)
class ExitHandling:
    """What ``cancel_external_run`` does once the process is gone.

    *wait* runs the grace wait and SIGKILL escalation on the caller's thread
    instead of in the background. *on_exit* runs after the process is
    confirmed gone (on whichever thread escalated), never while it may still
    be writing its own cancel-time reports; it is skipped if the process
    survives SIGKILL.
    """

    wait: bool = False
    on_exit: Callable[[], None] | None = None


def _stop_then(control: ProcessControl, pid: int, grace: float, after: ExitHandling) -> bool:
    """Escalate until *pid* is gone, then run ``after.on_exit``. True once it is gone."""
    gone = _escalate(control, pid, grace)
    if not gone:
        _logger.warning("pid %s survived SIGKILL; skipping post-exit work", pid)
    elif after.on_exit is not None:
        after.on_exit()
    return gone


def _escalate(control: ProcessControl, pid: int, grace: float) -> bool:
    """Wait *grace* for *pid* to honor SIGTERM, then SIGKILL it. True once it is gone."""
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


def cancel_external_run(
    project_uuid: str,
    run_id: str,
    reports_root: Path,
    *,
    grace_period_s: float | None = None,
    control: ProcessControl | None = None,
    after: ExitHandling | None = None,
) -> bool:
    """Stop an external run's process tree; escalate SIGTERM to SIGKILL after grace.

    *grace_period_s* defaults to ``config.services_env.cancel_grace_s()``
    (QUODEQ_CANCEL_GRACE_S, 30s): time to wait for the process to honor
    SIGTERM before escalating to SIGKILL. Long enough that graceful shutdown
    (per-dim scoring on cancel, status.json finalize, cache flush) finishes;
    short enough that the user isn't left waiting on a hung run.

    By default SIGTERM is sent here and the grace wait, SIGKILL escalation
    and ``after.on_exit`` run on ``control.start_background``, so the call
    returns at once and True means "stop is under way". With ``after.wait``
    all of that runs inline and True means the process is gone: a caller that
    deletes the run's files next (discard) needs that guarantee. Returns
    False only when there was nothing to cancel, or (``after.wait``) the
    process survived SIGKILL.
    """
    grace = grace_period_s if grace_period_s is not None else cancel_grace_s()
    control = control or ProcessControl()
    project_dir = resolve_child_dir(reports_root, project_uuid)
    if project_dir is None:
        return False
    pid = resolve_external_pid(Path(project_dir), run_id)
    if pid is None:
        return False

    after = after or ExitHandling()
    control.kill_tree(pid, signal.SIGTERM)
    if after.wait:
        return _stop_then(control, pid, grace, after)
    label = f"{_ESCALATION_THREAD_NAME}{pid}"
    control.start_background(
        lambda: run_isolated(lambda: _stop_then(control, pid, grace, after), label=label, log=_logger),
        label,
    )
    return True


def cancel_external_job(
    job_id: str, reports_root: Path, run_dir: Path | None, *,
    control: ProcessControl | None = None, after: ExitHandling | None = None,
) -> bool:
    """Stop the external run behind *job_id*; False when there is nothing to stop.

    *run_dir*, when it is a real folder, is trusted over a scan of
    *reports_root*. A run outside the reports folder (a PR review in
    $RUNNER_TEMP) is then addressed from its own folder,
    ``<root>/<project>/<run_id>``, so its .pid is found.
    """
    run_id = strip_external_prefix(job_id)
    if not is_safe_run_segment(run_id):
        return False
    root = run_dir.parent.parent if run_dir is not None and run_dir.is_dir() else reports_root
    project_uuid = resolve_external_run_project(root, run_id, run_dir_hint=run_dir)
    if project_uuid is None:
        return False
    return cancel_external_run(project_uuid, run_id, root, control=control, after=after)


def sync_indexed_run(db: sqlite3.Connection, job_id: str) -> bool:
    """Sync the run directory the index already knows for *job_id*.

    Returns False when there is no row or its run_dir is blank or gone, so
    the caller falls back to a wider sync. A blank run_dir counts as unknown:
    ``Path("")`` is ``Path(".")``, whose ``is_dir()`` is True, so it would
    sync the process cwd as if it were the run.
    """
    known = _run_index.get_run(db, job_id)
    run_dir = Path(known.run_dir) if known is not None and known.run_dir else None
    if run_dir is None or not run_dir.is_dir():
        return False
    _run_index.sync_index_for_run(db, run_dir)
    return True


def sync_external_run(db: sqlite3.Connection, job_id: str, reports_dir: Path) -> bool:
    """Bring the index row for an external run up to date; False if the id is unsafe.

    Prefers the run directory the index already knows, else scans for it.
    """
    run_id = strip_external_prefix(job_id)
    if not is_safe_run_segment(run_id):
        return False
    if not sync_indexed_run(db, job_id):
        sync_external_run_by_scan(db, reports_dir, run_id)
    return True
