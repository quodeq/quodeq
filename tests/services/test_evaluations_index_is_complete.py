"""EvaluationsIndex.is_complete() must not treat a LOST job as finished.

A job flips to LOST when the server restarts and its tracking thread is
gone, but the subprocess it was tracking may still be alive and writing.
Treating LOST as terminal is wrong for is_complete: doing so
would end an SSE tail on the internal id while the subprocess keeps
running. JOB_FINISHED (DONE/FAILED/CANCELLED only) is correct here --
LOST falls through to the on-disk status.json/scan.json check instead.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.job_status import JobStatus
from quodeq.data.fs.run_status_store import RunState, RunStatus, write_status
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import InMemoryJobStore, Job
from quodeq.services.jobs import JobManager


def _make_index(tmp_path: Path, job: Job) -> EvaluationsIndex:
    store = InMemoryJobStore()
    store.put(job)
    jobs = JobManager(job_store=store, reports_root=tmp_path / "reports")
    return EvaluationsIndex(
        jobs=jobs,
        index_db_path=tmp_path / "index.db",
        reports_root=tmp_path / "reports",
    )


def test_is_complete_false_for_lost_job_whose_run_is_still_running(tmp_path: Path) -> None:
    """A restart-orphaned LOST job whose subprocess is still writing status.json
    as "running" must NOT be reported complete -- the SSE tail must keep going."""
    project, run_id = "proj-lost", "run-lost"
    run_dir = tmp_path / "reports" / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        RunStatus(
            state=RunState.RUNNING,
            job_id="internal-lost-1",
            started_at="2026-05-22T19:00:00+00:00",
            dimensions=["security"],
        ),
    )
    job = Job(
        job_id="internal-lost-1",
        status=JobStatus.LOST,
        command=["python", "-m", "quodeq.cli", "evaluate"],
        started_at="2026-05-22T19:00:00+00:00",
        ended_at="2026-05-22T19:05:00+00:00",
        exit_code=None,
        output_project=project,
        output_run_id=run_id,
    )
    index = _make_index(tmp_path, job)
    assert index.is_complete("internal-lost-1") is False


def test_is_complete_true_for_lost_job_whose_run_actually_finished(tmp_path: Path) -> None:
    """A LOST job whose status.json shows a terminal state on disk is still
    reported complete -- the disk fallback, not the LOST status, decides."""
    project, run_id = "proj-lost-done", "run-lost-done"
    run_dir = tmp_path / "reports" / project / run_id
    run_dir.mkdir(parents=True)
    write_status(
        run_dir,
        RunStatus(
            state=RunState.DONE,
            job_id="internal-lost-2",
            started_at="2026-05-22T19:00:00+00:00",
            dimensions=["security"],
        ),
    )
    job = Job(
        job_id="internal-lost-2",
        status=JobStatus.LOST,
        command=["python", "-m", "quodeq.cli", "evaluate"],
        started_at="2026-05-22T19:00:00+00:00",
        ended_at="2026-05-22T19:05:00+00:00",
        exit_code=None,
        output_project=project,
        output_run_id=run_id,
    )
    index = _make_index(tmp_path, job)
    assert index.is_complete("internal-lost-2") is True
