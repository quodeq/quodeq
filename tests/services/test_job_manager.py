"""Tests for jobs.py: JobManager lifecycle (spawn failure, cancel, shutdown, get/list/delete, time limit)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


from quodeq.core.types import JobSnapshot
from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import (
    JobLaunchOptions,
    JobManager,
    JobProcessSeams,
    STATUS_RUNNING,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    _EXIT_CODE_SPAWN_FAILURE,
)
from tests._timeouts import budget


def _wait_for_job(manager: JobManager, job_id: str, timeout: float = 5.0) -> JobSnapshot | None:
    """Poll until the job reaches a terminal state.

    Scaled at the point of use so callers passing an explicit *timeout* still
    get the loaded-runner headroom.
    """
    import time
    deadline = time.monotonic() + budget(timeout)
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

        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=InMemoryJobStore())
        snap = mgr.start_job(["nonexistent"])
        assert snap.status == STATUS_FAILED
        assert snap.exit_code == _EXIT_CODE_SPAWN_FAILURE
        assert snap.error is not None

    def test_returns_failed_snapshot_on_subprocess_error(self):
        def bad_spawn(*args, **kwargs):
            raise subprocess.SubprocessError("spawn fail")

        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=InMemoryJobStore())
        snap = mgr.start_job(["bad"])
        assert snap.status == STATUS_FAILED
        assert snap.exit_code == _EXIT_CODE_SPAWN_FAILURE

    def test_spawn_failure_returns_friendly_error_not_raw_exception(self):
        def bad_spawn(*args, **kwargs):
            raise OSError(2, "No such file or directory", "/some/internal/path")

        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=InMemoryJobStore())
        snap = mgr.start_job(["nonexistent"])

        assert snap.error == "Failed to start the evaluation process. Check the server logs for details."
        assert "/some/internal/path" not in snap.error

    def test_spawn_failure_still_logs_raw_detail_server_side(self):
        store = InMemoryJobStore()
        log = MagicMock()

        def bad_spawn(*args, **kwargs):
            raise OSError(2, "No such file or directory", "/some/internal/path")

        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=store, log=log)
        snap = mgr.start_job(["nonexistent"])

        job = store.get(snap.job_id)
        assert any("/some/internal/path" in line for line in job.logs)
        assert any("/some/internal/path" in call.args[0] for call in log.error.call_args_list)


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


class TestDeleteJob:
    # EvaluationsIndex.delete drops the run dir and index row, then calls
    # JobManager.delete to remove the in-memory/persisted job entry. Before
    # this method existed the hasattr-guarded call was a silent no-op, so a
    # discarded run kept resurfacing in /api/evaluations for up to 24h from
    # the persisted job store.
    def test_delete_removes_terminal_job(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "done", [], "now", "later", 0))
        mgr = JobManager(job_store=store)
        assert mgr.delete("j1") is True
        assert mgr.get_job("j1") is None

    def test_delete_refuses_running_job(self):
        store = InMemoryJobStore()
        store.put(Job("j1", "running", [], "now", None, None))
        mgr = JobManager(job_store=store)
        assert mgr.delete("j1") is False
        assert mgr.get_job("j1") is not None

    def test_delete_missing_job_returns_false(self):
        mgr = JobManager(job_store=InMemoryJobStore())
        assert mgr.delete("nope") is False


class TestStartJobTimeLimit:
    def test_time_limit_carried_into_snapshot(self):
        # The progress route resolves the per-dim budget bar from the job
        # snapshot; before this field existed it read a nonexistent
        # `options` attribute and the budget was always None.
        def bad_spawn(*args, **kwargs):
            raise OSError("boom")

        # Spawn-failure path avoids threads; time_limit_s is set before spawn
        # so it must survive into the failure snapshot too.
        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=InMemoryJobStore())
        snap = mgr.start_job(["cmd"], JobLaunchOptions(time_limit_s=600))
        assert snap.time_limit_s == 600

    def test_time_limit_zero_carried(self):
        def bad_spawn(*args, **kwargs):
            raise OSError("boom")

        mgr = JobManager(JobProcessSeams(spawn_impl=bad_spawn), job_store=InMemoryJobStore())
        snap = mgr.start_job(["cmd"], JobLaunchOptions(time_limit_s=0))
        assert snap.time_limit_s == 0


def test_list_jobs_warns_on_deprecated_reports_root_kwarg(tmp_path):
    """Passing reports_root= to list_jobs emits DeprecationWarning and is ignored.

    External runs have been served via the SQLite index for some time; this
    kwarg was left for transitional compat and should stop being used.
    """
    import warnings

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
