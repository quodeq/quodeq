from __future__ import annotations

import io
import threading

import pytest

from quodeq.provider.jobs import JobManager


class FakeProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


def _make_manager_with_event(spawn_impl, job_id_holder: list) -> tuple[JobManager, threading.Event]:
    """Create a JobManager that signals *done* when the job completes."""
    done = threading.Event()

    def _on_complete(jid, _job):
        if not job_id_holder or jid == job_id_holder[0]:
            done.set()

    manager = JobManager(spawn_impl=spawn_impl, on_job_complete=_on_complete)
    return manager, done


@pytest.fixture()
def completed_success_job() -> dict:
    """Run a successful job and return the final result dict."""
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(
            stdout="Report path: /app/reports/sample-project/20260220/evaluation\nhello\n",
            stderr="warning\n",
            returncode=0,
        )

    job_id_holder: list[str] = []
    manager, done = _make_manager_with_event(spawn_impl, job_id_holder)
    job = manager.start_job(["echo", "ok"])
    job_id_holder.append(job["jobId"])
    done.wait(timeout=5.0)
    result = manager.get_job(job["jobId"])
    assert result is not None
    return result


def test_successful_job_status(completed_success_job: dict) -> None:
    assert completed_success_job["status"] == "done"


def test_successful_job_exit_code(completed_success_job: dict) -> None:
    assert completed_success_job["exitCode"] == 0


def test_successful_job_captures_logs(completed_success_job: dict) -> None:
    assert any("hello" in line for line in completed_success_job["logs"])


def test_successful_job_parses_output_project(completed_success_job: dict) -> None:
    assert completed_success_job["outputProject"] == "sample-project"


def test_successful_job_parses_output_run_id(completed_success_job: dict) -> None:
    assert completed_success_job["outputRunId"] == "20260220"


def test_job_manager_handles_failure() -> None:
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(stdout="", stderr="boom\n", returncode=2)

    job_id_holder: list[str] = []
    manager, done = _make_manager_with_event(spawn_impl, job_id_holder)
    job = manager.start_job(["false"])
    job_id_holder.append(job["jobId"])

    done.wait(timeout=5.0)
    result = manager.get_job(job["jobId"])
    assert result is not None

    assert result["status"] == "failed"
    assert result["exitCode"] == 2
    assert any("boom" in line for line in result["logs"])
