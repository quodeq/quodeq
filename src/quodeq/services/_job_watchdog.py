"""Watchdog decision logic for JobManager._monitor_process.

Split out of jobs.py as free functions. ``JobManager``'s own
``_watchdog_should_kill``/``_run_status_exit_reason`` methods become thin
delegates that call these, passing in the collaborators (store,
reports_root, cap, grace) the instance already owns.

``watchdog_should_kill`` takes ``grace_s`` as a plain parameter rather than
reading ``WATCHDOG_DEADLINE_GRACE_S`` off the ``jobs`` module itself:
``JobManager.__init__`` captures the constant once, at construction, into
``self._watchdog_grace_s``, and ``_watchdog_should_kill`` passes that
snapshot through. Tests that monkeypatch
``quodeq.services.jobs.WATCHDOG_DEADLINE_GRACE_S`` *before* constructing the
manager still see it take effect (the module global is read at construction
time); a patch after construction no longer changes an already-built
manager's grace, by design.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.services.wiring import read_run_status_json

if TYPE_CHECKING:
    from quodeq.services._job_model import Job, JobStore


def watchdog_should_kill(
    job_id: str, started_at: float, *, store: "JobStore", job_timeout_cap_s: float,
    grace_s: float, clock: Callable[[], float] = time.time,
) -> bool:
    """Return True when the watchdog should SIGKILL the job process now."""
    now = clock()
    if job_timeout_cap_s > 0 and (now - started_at) > job_timeout_cap_s:
        return True
    job = store.get(job_id)
    deadline_at = getattr(job, "deadline_at", None) if job else None
    if not deadline_at:
        return False
    try:
        deadline = datetime.fromisoformat(deadline_at).timestamp()
    except (TypeError, ValueError):
        return False
    return now > deadline + grace_s


def run_status_exit_reason(job: "Job | None", reports_root: Path | None) -> str | None:
    """Best-effort read of the run's ``status.json`` ``exit_reason``.

    The analysis loops break out at the deadline without raising, and the
    lifecycle records ``exit_reason="deadline"`` (see
    ``cli_evaluation.record_deadline_if_hit``). When the process then
    exits nonzero without the job watchdog ever firing, this is the only
    signal that the exit was a time-limit truncation, not a failure.
    """
    if job is None or not job.output_project or not job.output_run_id or reports_root is None:
        return None
    run_dir = reports_root / job.output_project / job.output_run_id
    data = read_run_status_json(run_dir)
    reason = data.get("exit_reason") if isinstance(data, dict) else None
    return reason if isinstance(reason, str) else None
