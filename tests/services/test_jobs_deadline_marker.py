"""Tests for analyzing_start marker propagating deadline_at to the Job."""
import json
from datetime import datetime, timezone, timedelta

from quodeq.services.jobs import JobManager
from quodeq.services._job_model import Job


def _job():
    return Job(
        job_id="j1",
        status="running",
        command=["quodeq"],
        started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=None,
        exit_code=None,
    )


def test_analyzing_start_marker_records_deadline_on_job():
    job = _job()
    deadline_iso = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
    line = json.dumps({"_cc": "analyzing_start", "deadline_at": deadline_iso, "budget_s": 600})

    JobManager._apply_marker(job, line)

    assert job.deadline_at == deadline_iso


def test_analyzing_start_marker_with_no_deadline_keeps_none():
    job = _job()
    line = json.dumps({"_cc": "analyzing_start", "deadline_at": None, "budget_s": 0})

    JobManager._apply_marker(job, line)

    assert job.deadline_at is None


def test_to_dict_includes_deadline_at():
    job = _job()
    job.deadline_at = "2026-05-02T10:00:00+00:00"
    snapshot = job.to_dict()
    assert snapshot.deadline_at == "2026-05-02T10:00:00+00:00"
