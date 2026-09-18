"""Tests for jobs.py: JobManager._monitor_process (completion, callbacks, watchdog kills)."""

from __future__ import annotations

import io
import subprocess
import threading


from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import (
    JobManager,
    STATUS_RUNNING,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
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
        # Group-wide terminate would signal a real pid; stub it to the fake's kill.
        monkeypatch.setattr(jobs_mod, "_terminate_process", lambda p: p.kill())

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)

        proc = _NeverExitsProcess()
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert proc.killed is True
        assert job.exit_code == _EXIT_CODE_TIMEOUT
        # Watchdog kills are time-budget exits, not failures: the header
        # renders them as "time limit reached" via the exit_reason.
        assert job.status == STATUS_CANCELLED
        assert job.exit_reason == "deadline"

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
        # The watchdog must terminate the whole process tree, not just the
        # parent PID; patch it to the stub's own kill so the loop can break.
        monkeypatch.setattr(jobs_mod, "_terminate_process", lambda p: p.kill())

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
        # Deadline kill = the user's own time budget doing its job.
        assert job.status == STATUS_CANCELLED
        assert job.exit_reason == "deadline"

    def test_watchdog_kill_terminates_the_process_tree(self, monkeypatch):
        """The watchdog must kill the process GROUP, not just the parent PID.

        The subprocess is spawned start_new_session=True, so a bare
        process.kill() SIGKILLs only the parent — the subagent pool + AI-CLI
        children are orphaned (token/CPU leak) and can keep writing into the
        abandoned run dir. Every other kill path goes through
        _terminate_process (group-wide, TERM->grace->KILL); the watchdog
        must too.
        """
        from quodeq.services import jobs as jobs_mod
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "0.05")
        monkeypatch.setattr(jobs_mod, "_WATCHDOG_POLL_INTERVAL_S", 0.01)
        calls = []

        def fake_terminate(p):
            calls.append(p)
            p.kill()  # let the stub's wait() start returning so the loop ends

        monkeypatch.setattr(jobs_mod, "_terminate_process", fake_terminate)

        store = InMemoryJobStore()
        mgr = JobManager(job_store=store)
        job = Job("j1", STATUS_RUNNING, ["cmd"], "now", None, None)
        store.put(job)
        proc = _NeverExitsProcess()
        mgr._processes["j1"] = proc
        mgr._monitor_process("j1", proc)

        assert calls == [proc], "watchdog kill must go through _terminate_process"
        assert job.exit_code == _EXIT_CODE_TIMEOUT
        assert job.status == STATUS_CANCELLED


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
