"""JobManager's start_job concurrency cap and cancel_job's run_dir hint.

Split from test_job_manager.py (672 lines, already at the file-length
ratchet) rather than growing it further. Covers findings 5400 (cancel_job's
scan of every project dir) and 5401 (start_job's unbounded thread spawning).
"""
from __future__ import annotations

import io
import subprocess
import threading
from pathlib import Path

import pytest

from quodeq.services._job_model import InMemoryJobStore
from quodeq.services.jobs import JobManager, STATUS_FAILED


class _NeverExitsProcess:
    """Subprocess stub that stays "running" until the fixture stops it.

    wait() blocks on an Event instead of raising TimeoutExpired in a tight
    loop, so the watchdog thread started by ``start_job`` sleeps rather than
    spins, and exits promptly once the fixture tears down.
    """

    pid = 4242

    def __init__(self) -> None:
        self.stdout = io.StringIO("")
        self._stop = threading.Event()

    def wait(self, timeout=None):
        if self._stop.wait(timeout=timeout):
            return 0
        raise subprocess.TimeoutExpired(cmd="cmd", timeout=timeout)

    def kill(self) -> None:
        self._stop.set()


@pytest.fixture
def fake_spawn():
    """spawn_impl handing out never-exiting processes; all stopped on teardown."""
    created: list[_NeverExitsProcess] = []

    def spawn(*args, **kwargs):
        proc = _NeverExitsProcess()
        created.append(proc)
        return proc

    yield spawn
    for proc in created:
        proc.kill()


class TestConcurrencyCap:
    def test_start_job_refuses_past_the_concurrency_cap(self, monkeypatch, fake_spawn):
        monkeypatch.setenv("QUODEQ_MAX_CONCURRENT_JOBS", "2")
        manager = JobManager(spawn_impl=fake_spawn, job_store=InMemoryJobStore())
        manager.start_job(["x"])
        manager.start_job(["x"])
        third = manager.start_job(["x"])
        assert third.error and "QUODEQ_MAX_CONCURRENT_JOBS" in third.error
        assert third.status == STATUS_FAILED

    def test_start_job_uses_a_default_cap_of_eight_when_env_unset(self, monkeypatch, fake_spawn):
        monkeypatch.delenv("QUODEQ_MAX_CONCURRENT_JOBS", raising=False)
        manager = JobManager(spawn_impl=fake_spawn, job_store=InMemoryJobStore())
        for _ in range(8):
            snap = manager.start_job(["x"])
            assert snap.status != STATUS_FAILED
        ninth = manager.start_job(["x"])
        assert ninth.status == STATUS_FAILED
        assert "QUODEQ_MAX_CONCURRENT_JOBS" in ninth.error

    def test_start_job_allows_a_new_job_once_a_slot_frees_up(self, monkeypatch, fake_spawn):
        monkeypatch.setenv("QUODEQ_MAX_CONCURRENT_JOBS", "1")
        manager = JobManager(spawn_impl=fake_spawn, job_store=InMemoryJobStore())
        first = manager.start_job(["x"])
        refused = manager.start_job(["x"])
        assert refused.status == STATUS_FAILED

        with manager._lock:
            manager._processes.pop(first.job_id, None)

        allowed = manager.start_job(["x"])
        assert allowed.status != STATUS_FAILED


class TestCancelExternalRunDirHint:
    def test_cancel_job_with_a_run_dir_hint_skips_the_reports_root_scan(
        self, tmp_path, monkeypatch,
    ):
        reports_root = tmp_path / "reports"
        run_dir = reports_root / "proj1" / "run1"
        run_dir.mkdir(parents=True)

        def explode(self):
            raise AssertionError("reports_root must not be scanned when a run_dir hint is given")

        monkeypatch.setattr(Path, "iterdir", explode)

        calls: dict = {}

        def fake_cancel_external_run(project_uuid, run_id, root, **kwargs):
            calls["project_uuid"] = project_uuid
            calls["run_id"] = run_id
            return True

        monkeypatch.setattr(
            "quodeq.services._external_jobs.cancel_external_run", fake_cancel_external_run,
        )

        manager = JobManager(job_store=InMemoryJobStore())
        result = manager.cancel_job("ext-run1", reports_root=reports_root, run_dir=run_dir)

        assert result is True
        assert calls == {"project_uuid": "proj1", "run_id": "run1"}

    def test_cancel_job_without_a_hint_still_falls_back_to_the_scan(self, tmp_path, monkeypatch):
        reports_root = tmp_path / "reports"
        (reports_root / "proj1" / "run1").mkdir(parents=True)

        calls: dict = {}

        def fake_cancel_external_run(project_uuid, run_id, root, **kwargs):
            calls["project_uuid"] = project_uuid
            return True

        monkeypatch.setattr(
            "quodeq.services._external_jobs.cancel_external_run", fake_cancel_external_run,
        )

        manager = JobManager(job_store=InMemoryJobStore())
        result = manager.cancel_job("ext-run1", reports_root=reports_root)

        assert result is True
        assert calls == {"project_uuid": "proj1"}
