"""Watchdog decision logic for JobManager._monitor_process.

Split out of jobs.py (Task 13) as free functions. ``JobManager``'s own
``_watchdog_should_kill``/``_run_status_exit_reason`` methods become thin
delegates that call these, passing in the collaborators (store,
reports_root, cap) the instance already owns.

``watchdog_should_kill`` looks up ``_WATCHDOG_DEADLINE_GRACE_S`` on the
``jobs`` module at call time (deferred, in-function) rather than importing
it directly: tests monkeypatch ``quodeq.services.jobs._WATCHDOG_DEADLINE_GRACE_S``
to shrink the grace window, and a top-level import here would bind its own
copy and silently escape that patch. The same deferred pattern is used for
``_publish_git.py``'s lookups of ``shared_publish.run_git`` (Task 12).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.services._job_model import Job, JobStore


def watchdog_should_kill(job_id: str, started_at: float, *, store: "JobStore", job_timeout_cap_s: float) -> bool:
    """Return True when the watchdog should SIGKILL the job process now."""
    from quodeq.services import jobs as _jobs

    now = time.time()
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
    return now > deadline + _jobs._WATCHDOG_DEADLINE_GRACE_S


def run_status_exit_reason(job: "Job | None", reports_root: Path | None) -> str | None:
    """Best-effort read of the run's ``status.json`` ``exit_reason``.

    The analysis loops break out at the deadline without raising, and the
    lifecycle records ``exit_reason="deadline"`` (see
    ``_cli_evaluation._record_deadline_if_hit``). When the process then
    exits nonzero without the job watchdog ever firing, this is the only
    signal that the exit was a time-limit truncation, not a failure.
    """
    if job is None or not job.output_project or not job.output_run_id or reports_root is None:
        return None
    status_path = reports_root / job.output_project / job.output_run_id / "status.json"
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    reason = data.get("exit_reason")
    return reason if isinstance(reason, str) else None
