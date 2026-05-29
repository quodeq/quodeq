from __future__ import annotations

import io
import threading
from pathlib import Path

import pytest

from quodeq.core.types import JobSnapshot
from quodeq.services.jobs import JobManager

_FAKE_REPORT_PATH = "Report path: /app/reports/sample-project/20260220/evaluation"
_TEST_TIMEOUT_S = 5.0


class FakeProcess:
    """Simulate a subprocess with merged stdout/stderr (subprocess.STDOUT)."""
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        # Merge stderr into stdout to match real subprocess.STDOUT behaviour
        self.stdout = io.StringIO(stdout + stderr)
        self._returncode = returncode

    def wait(self, timeout=None) -> int:
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
def completed_success_job() -> JobSnapshot:
    """Run a successful job and return the final result snapshot."""
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(
            stdout=_FAKE_REPORT_PATH + "\nhello\n",
            stderr="warning\n",
            returncode=0,
        )

    job_id_holder: list[str] = []
    manager, done = _make_manager_with_event(spawn_impl, job_id_holder)
    job = manager.start_job(["echo", "ok"])
    job_id_holder.append(job.job_id)
    done.wait(timeout=_TEST_TIMEOUT_S)
    result = manager.get_job(job.job_id)
    assert result is not None
    return result


def test_successful_job_status(completed_success_job: JobSnapshot) -> None:
    assert completed_success_job.status == "done"


def test_successful_job_exit_code(completed_success_job: JobSnapshot) -> None:
    assert completed_success_job.exit_code == 0


def test_successful_job_captures_logs(completed_success_job: JobSnapshot) -> None:
    assert any("hello" in line for line in completed_success_job.logs)


def test_successful_job_parses_output_project(completed_success_job: JobSnapshot) -> None:
    assert completed_success_job.output_project == "sample-project"


def test_successful_job_parses_output_run_id(completed_success_job: JobSnapshot) -> None:
    assert completed_success_job.output_run_id == "20260220"


def test_markers_parsed_from_merged_stream() -> None:
    """Structured markers in stdout update job phase and dimensions."""
    marker_setup = '{"_cc": "setup", "dimensions": ["security", "performance"]}\n'
    marker_analyzing = '{"_cc": "analyzing", "dimension": "security"}\n'
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(
            stdout=marker_setup + marker_analyzing + "Report path: /r/proj/run1/evaluation\n",
            returncode=0,
        )

    job_id_holder: list[str] = []
    manager, done = _make_manager_with_event(spawn_impl, job_id_holder)
    job = manager.start_job(["echo"])
    job_id_holder.append(job.job_id)
    done.wait(timeout=_TEST_TIMEOUT_S)
    result = manager.get_job(job.job_id)
    assert result is not None
    assert result.phase == "analyzing"
    assert result.dimensions == ["security", "performance"]
    assert result.current_dimension == "security"
    # Markers should NOT appear in logs
    assert not any("_cc" in line for line in result.logs)


def test_job_manager_handles_failure() -> None:
    def spawn_impl(*_args, **_kwargs):
        return FakeProcess(stdout="", stderr="boom\n", returncode=2)

    job_id_holder: list[str] = []
    manager, done = _make_manager_with_event(spawn_impl, job_id_holder)
    job = manager.start_job(["false"])
    job_id_holder.append(job.job_id)

    done.wait(timeout=_TEST_TIMEOUT_S)
    result = manager.get_job(job.job_id)
    assert result is not None

    assert result.status == "failed"
    assert result.exit_code == 2
    assert any("boom" in line for line in result.logs)


def test_start_evaluation_forwards_provider_and_model(tmp_path: Path) -> None:
    """start_evaluation must pass ai_provider/ai_model through the dispatcher."""
    from unittest.mock import patch
    from quodeq.services.base import EvaluationOptions
    from quodeq.services.evaluation_mixin import FsEvaluationMixin

    captured: dict = {}

    class _SpyDispatcher:
        def dispatch(self, cmd, *, cwd=None, env=None, ai_provider=None, ai_model=None):
            captured["ai_provider"] = ai_provider
            captured["ai_model"] = ai_model
            return JobSnapshot(job_id="job-1", status="running")

    mixin = FsEvaluationMixin()
    mixin._jobs = None  # not used — spy bypasses JobManager entirely
    mixin._dispatcher = _SpyDispatcher()

    opts = EvaluationOptions(ai_cmd="ollama", ai_model="gemma4:26b-mlx")
    with patch("quodeq.services.evaluation_mixin._register_project"):
        mixin.start_evaluation(str(tmp_path), str(tmp_path / "reports"), opts)

    assert captured["ai_provider"] == "ollama"
    assert captured["ai_model"] == "gemma4:26b-mlx"
