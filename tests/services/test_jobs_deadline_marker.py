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


def test_deadline_extended_marker_updates_deadline_on_job():
    """The pool auto-scale emits deadline_extended mid-run; the watchdog's
    deadline must follow it, else it kills a healthy run at the ORIGINAL
    deadline while the pool believes it has hours left."""
    job = _job()
    first = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    JobManager._apply_marker(
        job, json.dumps({"_cc": "analyzing_start", "deadline_at": first, "budget_s": 60})
    )
    extended = (datetime.now(timezone.utc) + timedelta(seconds=7200)).isoformat()

    JobManager._apply_marker(
        job,
        json.dumps(
            {"_cc": "deadline_extended", "deadline_at": extended, "budget_s": 7200}
        ),
    )

    assert job.deadline_at == extended


def test_watchdog_grace_covers_a_full_drain():
    """The watchdog exists to reap HUNG runs, never to cut loaded agents.
    Past the deadline the pool stops dispatching and in-flight calls drain;
    the longest legitimate in-flight call is one scaled local read timeout
    (500s x subagents, realistically up to 3). The grace must exceed that,
    or the watchdog SIGTERMs a healthy drain and the batch's work is lost."""
    from quodeq.analysis._api_runner import _LOCAL_TIMEOUT
    from quodeq.services import jobs as jobs_mod

    assert jobs_mod._WATCHDOG_DEADLINE_GRACE_S >= _LOCAL_TIMEOUT.read * 3
