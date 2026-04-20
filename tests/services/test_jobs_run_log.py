from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.services.jobs import JobManager, STATUS_RUNNING
from quodeq.services._job_model import Job


def test_consume_stream_tees_to_run_log(tmp_path: Path) -> None:
    """Once the report_path marker arrives, subsequent lines land in run.log."""
    project = "proj-uuid"
    run_id = "run-A"
    run_dir = tmp_path / project / run_id
    run_dir.mkdir(parents=True)

    jm = JobManager(reports_root=tmp_path)
    job = Job(
        job_id="job-1",
        status=STATUS_RUNNING,
        command=["x"],
        started_at="2026-04-20T00:00:00+00:00",
        ended_at=None,
        exit_code=None,
    )
    jm._store.put(job)  # internal — test helper

    marker = json.dumps({"_cc": "report_path", "project": project, "runId": run_id})
    stream = iter([
        "pre-marker line\n",
        marker + "\n",
        "post-marker line\n",
    ])
    jm._consume_stream("job-1", stream)

    contents = (run_dir / "run.log").read_text()
    # Both pre-marker (buffered) and post-marker lines must appear, in order.
    assert "pre-marker line" in contents
    assert "post-marker line" in contents
    assert contents.index("pre-marker line") < contents.index("post-marker line")


def test_consume_stream_no_run_dir_silent(tmp_path: Path) -> None:
    """If no report_path marker ever arrives, consume_stream completes without error."""
    jm = JobManager(reports_root=tmp_path)
    job = Job(
        job_id="job-2", status=STATUS_RUNNING, command=["x"],
        started_at="2026-04-20T00:00:00+00:00", ended_at=None, exit_code=None,
    )
    jm._store.put(job)
    jm._consume_stream("job-2", iter(["line-1\n", "line-2\n"]))
    # No run.log anywhere — nothing to assert beyond "did not raise".
