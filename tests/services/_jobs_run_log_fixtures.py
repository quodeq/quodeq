"""Shared running-job builder for tests/services/test_jobs_run_log*.py."""
from __future__ import annotations

from quodeq.core.run.job_status import JobStatus
from quodeq.services._job_model import Job


def _make_job(job_id: str) -> Job:
    return Job(
        job_id=job_id,
        status=JobStatus.RUNNING,
        command=["x"],
        started_at="2026-04-20T00:00:00+00:00",
        ended_at=None,
        exit_code=None,
    )
