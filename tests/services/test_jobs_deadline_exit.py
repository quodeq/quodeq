"""Deadline-killed jobs surface a time-limit terminal state, not FAILED.

When the watchdog kills a run at its deadline (or the run's own status.json
records exit_reason="deadline"/"time_limit" from PR #956), the job must end
as status="cancelled" with exit_reason set, so the evaluate header can render
"time limit reached" (non-error) consistent with the coverage banner below
it. "cancelled" is already in the salvage-scoring trigger list in
api/_evaluation_routes.py, so completed dimensions still get scored.
"""

from __future__ import annotations

import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quodeq.services._job_model import (
    InMemoryJobStore,
    Job,
)
from quodeq.services._job_file_store import (
    _job_from_json,
    _job_to_json,
)
from quodeq.services.jobs import (
    JobManager,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_RUNNING,
    _EXIT_CODE_TIMEOUT,
)


class _NeverExitsProcess:
    """Subprocess stub: every wait(timeout=...) raises TimeoutExpired until killed."""

    pid = 123

    def __init__(self):
        self.stdout = io.StringIO("")
        self.killed = False

    def wait(self, timeout=None):
        if self.killed:
            return -9
        raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)

    def kill(self):
        self.killed = True


class _ExitsWith:
    """Subprocess stub that exits immediately with the given return code."""

    pid = 124

    def __init__(self, returncode: int):
        self.stdout = io.StringIO("")
        self._returncode = returncode

    def wait(self, timeout=None):
        return self._returncode


def _running_job(**kwargs) -> Job:
    return Job(
        job_id="j1",
        status=STATUS_RUNNING,
        command=["quodeq"],
        started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=None,
        exit_code=None,
        **kwargs,
    )


def _write_status_json(reports_root: Path, project: str, run_id: str, exit_reason) -> None:
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({"state": "cancelled", "exit_reason": exit_reason}),
        encoding="utf-8",
    )


class TestWatchdogDeadlineKill:
    def test_watchdog_kill_marks_job_cancelled_with_deadline_reason(self, monkeypatch):
        """A watchdog kill is the time budget doing its job, not a failure."""
        from quodeq.services import jobs as jobs_mod

        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_DEADLINE_GRACE_S", 0.02)
        monkeypatch.setattr(jobs_mod, "_terminate_process", lambda p: p.kill())

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        job = _running_job(deadline_at=past)
        store.put(job)
        proc = _NeverExitsProcess()
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert proc.killed is True
        assert job.status == STATUS_CANCELLED
        assert job.exit_reason == "deadline"
        assert job.exit_code == _EXIT_CODE_TIMEOUT


class TestRunStatusDeadlineFallback:
    """The analysis side can exit on its own after recording a deadline.

    The loops in analysis/_loops.py break out at the deadline without the
    watchdog ever firing; if the process then exits nonzero, the run's
    status.json exit_reason is the only signal that this was a time-limit
    exit rather than a real failure.
    """

    def _manager(self, tmp_path: Path) -> tuple[JobManager, Job]:
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store, reports_root=tmp_path)
        job = _running_job(output_project="proj", output_run_id="run1")
        store.put(job)
        return mgr, job

    def test_nonzero_exit_with_run_deadline_reason_is_cancelled(self, tmp_path):
        mgr, job = self._manager(tmp_path)
        _write_status_json(tmp_path, "proj", "run1", "deadline")
        proc = _ExitsWith(1)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_CANCELLED
        assert job.exit_reason == "deadline"
        assert job.exit_code == 1

    def test_time_limit_reason_preserved_verbatim(self, tmp_path):
        mgr, job = self._manager(tmp_path)
        _write_status_json(tmp_path, "proj", "run1", "time_limit")
        proc = _ExitsWith(1)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_CANCELLED
        assert job.exit_reason == "time_limit"

    def test_other_exit_reason_stays_failed(self, tmp_path):
        """Only time-budget reasons soften the failure; provider deaths etc.
        must keep surfacing as FAILED."""
        mgr, job = self._manager(tmp_path)
        _write_status_json(tmp_path, "proj", "run1", "provider_fatal")
        proc = _ExitsWith(1)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_FAILED
        assert job.exit_reason is None

    def test_missing_status_json_stays_failed(self, tmp_path):
        mgr, job = self._manager(tmp_path)
        proc = _ExitsWith(1)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_FAILED
        assert job.exit_reason is None

    def test_corrupt_status_json_stays_failed(self, tmp_path):
        mgr, job = self._manager(tmp_path)
        run_dir = tmp_path / "proj" / "run1"
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text("not json", encoding="utf-8")
        proc = _ExitsWith(1)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_FAILED
        assert job.exit_reason is None

    def test_clean_exit_stays_done_even_with_deadline_reason(self, tmp_path):
        """A rc=0 deadline-truncated run keeps DONE; the coverage banner
        already tells the truncation story from status.json."""
        mgr, job = self._manager(tmp_path)
        _write_status_json(tmp_path, "proj", "run1", "deadline")
        proc = _ExitsWith(0)
        mgr._processes["j1"] = proc

        mgr._monitor_process("j1", proc)

        assert job.status == STATUS_DONE
        assert job.exit_reason is None


class TestExitReasonSerialization:
    def test_to_dict_carries_exit_reason(self):
        job = _running_job()
        job.exit_reason = "deadline"
        assert job.to_dict().exit_reason == "deadline"

    def test_json_round_trip_preserves_exit_reason(self):
        """FileJobStore persistence must not drop the reason across restarts."""
        job = _running_job()
        job.exit_reason = "deadline"
        assert _job_from_json(_job_to_json(job)).exit_reason == "deadline"
