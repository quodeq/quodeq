"""Tests for jobs.py — JobManager logic (spawn failures, cancellation, eviction, markers)."""

from __future__ import annotations

import io
import json
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import (
    JobManager,
    STATUS_RUNNING,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    _EXIT_CODE_SPAWN_FAILURE,
    _EXIT_CODE_TIMEOUT,
)


class FakeProcess:
    """Minimal subprocess mock."""

    def __init__(self, stdout="", returncode=0, pid=12345):
        self.stdout = io.StringIO(stdout)
        self._returncode = returncode
        self.pid = pid

    def wait(self, timeout=None):
        return self._returncode

    def kill(self):
        pass


def _wait_for_job(manager: JobManager, job_id: str, timeout: float = 5.0) -> JobSnapshot | None:
    """Poll until the job reaches a terminal state."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = manager.get_job(job_id)
        if snap and snap.status != STATUS_RUNNING:
            return snap
        time.sleep(0.05)
    return manager.get_job(job_id)


# ---------------------------------------------------------------------------
# Spawn failure
# ---------------------------------------------------------------------------


class TestStartJobSpawnFailure:
    def test_returns_failed_snapshot_on_os_error(self):
        def bad_spawn(*args, **kwargs):
            raise OSError("No such file")

        mgr = JobManager(spawn_impl=bad_spawn, job_store=InMemoryJobStore())
        snap = mgr.start_job(["nonexistent"])
        assert snap.status == STATUS_FAILED
        assert snap.exit_code == _EXIT_CODE_SPAWN_FAILURE
        assert snap.error is not None
        assert "No such file" in snap.error

    def test_returns_failed_snapshot_on_subprocess_error(self):
        def bad_spawn(*args, **kwargs):
            raise subprocess.SubprocessError("spawn fail")

        mgr = JobManager(spawn_impl=bad_spawn, job_store=InMemoryJobStore())
        snap = mgr.start_job(["bad"])
        assert snap.status == STATUS_FAILED
        assert snap.exit_code == _EXIT_CODE_SPAWN_FAILURE


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancelJob:
    def test_cancel_nonexistent_returns_false(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        assert mgr.cancel_job("no-such-id") is False

    def test_cancel_already_done_returns_false(self):
        store = InMemoryJobStore()
        store.put(Job("j1", STATUS_DONE, [], "now", "later", 0))
        mgr = JobManager(job_store=store)
        assert mgr.cancel_job("j1") is False

    @patch("quodeq.services.jobs._terminate_process")
    def test_cancel_running_job(self, mock_terminate):
        store = InMemoryJobStore()
        store.put(Job("j1", STATUS_RUNNING, [], "now", None, None))
        mgr = JobManager(job_store=store)
        # Simulate a tracked process
        fake_proc = MagicMock()
        fake_proc.pid = 999
        mgr._processes["j1"] = fake_proc
        assert mgr.cancel_job("j1") is True
        assert store.get("j1").status == STATUS_CANCELLED
        # Internal cancel must go through _terminate_process (TERM → grace →
        # SIGKILL); bare _kill_tree leaves orphans when the child is blocked
        # in a long socket read.
        mock_terminate.assert_called_once_with(fake_proc)


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    @patch("quodeq.services.jobs._kill_tree")
    def test_shutdown_kills_all(self, mock_kill):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        proc1 = MagicMock()
        proc1.pid = 100
        proc2 = MagicMock()
        proc2.pid = 200
        mgr._processes["j1"] = proc1
        mgr._processes["j2"] = proc2
        mgr.shutdown()
        assert mock_kill.call_count == 2
        assert mgr._processes == {}

    @patch("quodeq.services.jobs._kill_tree", side_effect=ProcessLookupError)
    def test_shutdown_ignores_dead_process(self, mock_kill):
        # Patch target must match the name used inside jobs.py (which did
        # `from quodeq.analysis._process import _kill_tree` at import time).
        # Patching the source module's attribute does not intercept the
        # already-bound reference here, and the real _kill_tree would run
        # os.killpg on PID 999 — which on Linux CI can be a live process,
        # sending SIGTERM to the test runner's process group.
        mgr = JobManager(job_store=InMemoryJobStore())
        mgr._processes["j1"] = MagicMock(pid=999)
        mgr.shutdown()  # should not raise
        assert mgr._processes == {}
        assert mock_kill.call_count == 1


# ---------------------------------------------------------------------------
# get_job / list_jobs
# ---------------------------------------------------------------------------


class TestGetAndListJobs:
    def test_get_job_returns_none_for_missing(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        assert mgr.get_job("nope") is None

    def test_get_job_returns_snapshot(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "done", ["echo"], "now", "later", 0))
        mgr = JobManager(job_store=store)
        snap = mgr.get_job("j1")
        assert snap is not None
        assert snap.job_id == "j1"

    def test_list_jobs(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "done", [], "now", "later", 0))
        store.put(Job("j2", "running", [], "now", None, None))
        mgr = JobManager(job_store=store)
        jobs = mgr.list_jobs()
        assert len(jobs) == 2
        assert {j.job_id for j in jobs} == {"j1", "j2"}


# ---------------------------------------------------------------------------
# _apply_marker
# ---------------------------------------------------------------------------


class TestApplyMarker:
    def _make_job(self):
        return Job("j1", "running", [], "now", None, None)

    def test_setup_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "setup", "dimensions": ["sec", "perf"]})
        JobManager._apply_marker(job, line)
        assert job.phase == "setup"
        assert job.dimensions == ["sec", "perf"]

    def test_analyzing_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "analyzing", "dimension": "security"})
        JobManager._apply_marker(job, line)
        assert job.phase == "analyzing"
        assert job.current_dimension == "security"

    def test_scoring_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "scoring", "dimension": "perf"})
        JobManager._apply_marker(job, line)
        assert job.phase == "scoring"
        assert job.current_dimension == "perf"

    def test_report_path_marker(self):
        job = self._make_job()
        line = json.dumps({"_cc": "report_path", "project": "myproj", "runId": "r1"})
        JobManager._apply_marker(job, line)
        assert job.output_project == "myproj"
        assert job.output_run_id == "r1"

    def test_report_path_marker_missing_fields(self):
        job = self._make_job()
        line = json.dumps({"_cc": "report_path"})
        JobManager._apply_marker(job, line)
        assert job.output_project is None

    def test_invalid_json_ignored(self):
        job = self._make_job()
        JobManager._apply_marker(job, "not json")
        assert job.phase is None


# ---------------------------------------------------------------------------
# _append_log
# ---------------------------------------------------------------------------


class TestAppendLog:
    def test_empty_line_ignored(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "")
        assert len(job.logs) == 0

    def test_marker_line_not_in_logs(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        marker = json.dumps({"_cc": "setup", "dimensions": ["sec"]})
        mgr._append_log(job, marker)
        assert len(job.logs) == 0
        assert job.phase == "setup"

    def test_ansi_stripped(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "\x1b[32mhello\x1b[0m")
        assert job.logs[0] == "hello"

    def test_fallback_report_path_extraction(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None)
        mgr._append_log(job, "Report path: /r/my-project/run123/evaluation")
        assert job.output_project == "my-project"
        assert job.output_run_id == "run123"

    def test_fallback_report_path_skipped_if_already_set(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        job = Job("j1", "running", [], "now", None, None, output_project="already")
        mgr._append_log(job, "Report path: /r/other/run2/evaluation")
        assert job.output_project == "already"  # not overwritten


# ---------------------------------------------------------------------------
# _consume_stream
# ---------------------------------------------------------------------------


class TestConsumeStream:
    def test_none_stream(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        mgr._consume_stream("j1", None)  # should not raise

    def test_consumes_lines(self):
        store = InMemoryJobStore()
        job = Job("j1", "running", [], "now", None, None)
        store.put(job)
        mgr = JobManager(job_store=store)
        stream = io.StringIO("line1\nline2\n")
        mgr._consume_stream("j1", stream)
        assert "line1" in job.logs
        assert "line2" in job.logs

    def test_stops_if_job_removed(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        # Job not in store — _flush_batch should return False
        stream = io.StringIO("line1\n")
        mgr._consume_stream("j1", stream)  # should not raise


# ---------------------------------------------------------------------------
# _evict_completed_jobs
# ---------------------------------------------------------------------------


class TestEvictCompletedJobs:
    def test_evicts_excess(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        from quodeq.services._job_model import _MAX_COMPLETED_JOBS
        # Add more than _MAX_COMPLETED_JOBS done jobs
        for i in range(_MAX_COMPLETED_JOBS + 5):
            store.put(Job(f"j{i}", "done", [], "now", "later", 0))
        mgr._evict_completed_jobs()
        remaining = store.list()
        assert len(remaining) == _MAX_COMPLETED_JOBS

    def test_running_not_evicted(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        store.put(Job("running1", "running", [], "now", None, None))
        store.put(Job("done1", "done", [], "now", "later", 0))
        mgr._evict_completed_jobs()
        assert store.get("running1") is not None


# ---------------------------------------------------------------------------
# _monitor_process
# ---------------------------------------------------------------------------


class TestMonitorProcess:
    def test_successful_completion(self):
        store = InMemoryJobStore()
        done_event = threading.Event()

        def on_complete(jid, job):
            done_event.set()

        mgr = JobManager(job_store=store, on_job_complete=on_complete)
        job = Job("j1", STATUS_RUNNING, ["echo"], "now", None, None)
        store.put(job)
        proc = FakeProcess(stdout="", returncode=0)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)
        assert job.status == STATUS_DONE
        assert job.exit_code == 0
        assert done_event.is_set()

    def test_failed_completion(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)
        proc = FakeProcess(returncode=1)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)
        assert job.status == STATUS_FAILED
        assert job.exit_code == 1

    def test_cancelled_job_not_overwritten(self):
        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_CANCELLED, ["cmd"], "now", "later", None)
        store.put(job)
        proc = FakeProcess(returncode=0)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)
        assert job.status == STATUS_CANCELLED  # not overwritten

    def test_callback_error_does_not_crash(self):
        store = InMemoryJobStore()

        def bad_callback(jid, job):
            raise RuntimeError("callback boom")

        mgr = JobManager(job_store=store, on_job_complete=bad_callback)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)
        proc = FakeProcess(returncode=0)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)  # should not raise
        assert job.status == STATUS_DONE

    def test_env_cap_kills_process(self, monkeypatch):
        """When QUODEQ_JOB_TIMEOUT_S is set, the watchdog kills past that cap
        even if no deadline_at was set on the job.
        """
        from quodeq.services import jobs as jobs_mod
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "0.05")
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)

        proc = _NeverExitsProcess()
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert proc.killed is True
        assert job.exit_code == _EXIT_CODE_TIMEOUT
        assert job.status == STATUS_FAILED

    def test_no_cap_no_deadline_does_not_kill(self, monkeypatch):
        """With no QUODEQ_JOB_TIMEOUT_S and no deadline_at, the watchdog must
        never preemptively kill — the user did not opt into a time cap.
        """
        from quodeq.services import jobs as jobs_mod
        monkeypatch.delenv("QUODEQ_JOB_TIMEOUT_S", raising=False)
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)

        # Process exits cleanly after a few poll cycles.
        proc = _ExitsAfter(returncode=0, exits_after_n_polls=3)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert proc.killed is False
        assert job.exit_code == 0
        assert job.status == STATUS_DONE

    def test_deadline_in_future_does_not_kill(self, monkeypatch):
        """Job with deadline_at in the future is not killed by the watchdog."""
        from datetime import datetime, timedelta, timezone
        from quodeq.services import jobs as jobs_mod
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None, deadline_at=future)
        store.put(job)

        proc = _ExitsAfter(returncode=0, exits_after_n_polls=3)
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert proc.killed is False
        assert job.status == STATUS_DONE

    def test_deadline_past_plus_grace_kills(self, monkeypatch):
        """Job whose deadline_at has passed (plus the grace window) is killed."""
        from datetime import datetime, timedelta, timezone
        from quodeq.services import jobs as jobs_mod
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_DEADLINE_GRACE_S", 0.02)

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None, deadline_at=past)
        store.put(job)

        proc = _NeverExitsProcess()
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert proc.killed is True
        assert job.exit_code == _EXIT_CODE_TIMEOUT
        assert job.status == STATUS_FAILED


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


class _ExitsAfter:
    """Subprocess stub that raises TimeoutExpired N times, then returns cleanly."""
    pid = 124

    def __init__(self, returncode: int, exits_after_n_polls: int):
        self.stdout = io.StringIO("")
        self._returncode = returncode
        self._remaining = exits_after_n_polls
        self.killed = False

    def wait(self, timeout=None):
        if self._remaining <= 0:
            return self._returncode
        self._remaining -= 1
        raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)

    def kill(self):
        self.killed = True


def test_list_jobs_warns_on_deprecated_reports_root_kwarg(tmp_path):
    """Passing reports_root= to list_jobs emits DeprecationWarning and is ignored.

    External runs have been served via the SQLite index since Plan B1/B2;
    this kwarg was left for transitional compat and should stop being used.
    """
    import warnings
    from quodeq.services.jobs import JobManager, InMemoryJobStore

    mgr = JobManager(job_store=InMemoryJobStore())

    # No warning when kwarg is omitted.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        mgr.list_jobs()  # must not raise

    # DeprecationWarning when kwarg is passed — ignored value is safe (empty list).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        result = mgr.list_jobs(reports_root=tmp_path)
    assert result == []
    assert any(
        issubclass(w.category, DeprecationWarning)
        and "reports_root" in str(w.message)
        for w in caught
    ), f"expected DeprecationWarning about reports_root, got: {[str(w.message) for w in caught]}"
