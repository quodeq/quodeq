from __future__ import annotations

import io
import time

from codecompass.action_provider_jobs import JobManager


class FakeProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


def test_job_manager_tracks_status_and_logs() -> None:
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(
            stdout="Report path: /app/reports/sample-project/20260220/evaluation\nhello\n",
            stderr="warning\n",
            returncode=0,
        )

    manager = JobManager(spawn_impl=spawn_impl)
    job = manager.start_job(["echo", "ok"])

    assert job["status"] in {"running", "done", "failed"}

    for _ in range(50):
        updated = manager.get_job(job["jobId"])
        if updated and updated["status"] != "running":
            job = updated
            break
        time.sleep(0.01)

    assert job["status"] == "done"
    assert job["exitCode"] == 0
    assert any("hello" in line for line in job["logs"])
    assert job["outputProject"] == "sample-project"
    assert job["outputRunId"] == "20260220"


def test_job_manager_handles_failure() -> None:
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(stdout="", stderr="boom\n", returncode=2)

    manager = JobManager(spawn_impl=spawn_impl)
    job = manager.start_job(["false"])

    for _ in range(50):
        updated = manager.get_job(job["jobId"])
        if updated and updated["status"] != "running":
            job = updated
            break
        time.sleep(0.01)

    assert job["status"] == "failed"
    assert job["exitCode"] == 2
    assert any("boom" in line for line in job["logs"])
