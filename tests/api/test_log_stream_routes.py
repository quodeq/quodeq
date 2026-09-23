"""Tests for GET /api/jobs/<id>/logs (plain JSON tail) and the log-stream route helpers."""
from __future__ import annotations

from http import HTTPStatus

from tests.api._log_stream_routes_fixtures import (  # noqa: F401 -- app is a pytest fixture
    _seed_run,
    app,
)


def test_plain_logs_returns_content(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-1-done", "first\nsecond\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-1-done/logs")
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["first", "second"]
    assert data["nextOffset"] == len("first\nsecond\n")
    assert data["done"] is True


def test_plain_logs_since_offset(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-2", "first\nsecond\nthird\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-2/logs?since=6")  # after "first\n"
    assert resp.status_code == HTTPStatus.OK
    data = resp.get_json()
    assert data["lines"] == ["second", "third"]


def test_plain_logs_404_when_log_missing(tmp_path, app) -> None:
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    app.config["_provider"].map["job-3"] = run_dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-3/logs")
    assert resp.status_code == HTTPStatus.NOT_FOUND


def test_plain_logs_410_when_run_dir_missing(tmp_path, app) -> None:
    app.config["_provider"].map["job-4"] = tmp_path / "gone"  # not a real dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-4/logs")
    assert resp.status_code == HTTPStatus.GONE


def test_plain_logs_partial_line_stripped(tmp_path, app) -> None:
    """If the last line lacks a trailing newline, it's not returned — caller polls again."""
    _seed_run(tmp_path, app, "job-5", "complete\npartial-tail")
    client = app.test_client()
    resp = client.get("/api/jobs/job-5/logs")
    data = resp.get_json()
    assert data["lines"] == ["complete"]
    assert data["nextOffset"] == len("complete\n")


def test_plain_logs_filters_resources_lines(tmp_path, app) -> None:
    """Resource snapshots stay in run.log for forensics but never reach the dashboard."""
    content = (
        "[INFO] [security] 0m10s | 1 active | 5 files taken\n"
        "[INFO] [resources] elapsed=1m00s rss=120MB threads=5 fds=8 ollama=200MB\n"
        "[INFO] [security] 0m20s | 1 active | 9 files taken\n"
    )
    _seed_run(tmp_path, app, "job-filter", content)
    client = app.test_client()
    data = client.get("/api/jobs/job-filter/logs").get_json()
    assert all("[resources]" not in line for line in data["lines"])
    assert any("[security]" in line for line in data["lines"])
    # Offset must still advance past the suppressed line so the next poll
    # doesn't replay it.
    assert data["nextOffset"] == len(content)


def test_plain_logs_rejects_traversal_job_id(tmp_path, app) -> None:
    client = app.test_client()
    resp = client.get("/api/jobs/../logs")
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()["code"] == "INVALID_INPUT"


def test_stream_logs_rejects_traversal_job_id(tmp_path, app) -> None:
    client = app.test_client()
    resp = client.get("/api/jobs/../logs/stream")
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()["code"] == "INVALID_INPUT"


def test_is_preparing_job_uses_public_get_job_not_private_store():
    """_is_preparing_job must work via JobManager.get_job(), not provider._jobs._store."""
    from quodeq.api._log_stream_routes import _is_preparing_job
    from quodeq.core.types.job import JobSnapshot

    class FakeJobs:
        def get_job(self, job_id):
            return JobSnapshot(job_id=job_id, status="running", output_project=None)
        # Deliberately no _store attribute — proves the route doesn't reach for it.

    class FakeProvider:
        _jobs = FakeJobs()

    assert _is_preparing_job(FakeProvider(), "job-1") is True


def test_stream_terminal_state_uses_public_get_job_not_private_store():
    """_stream_terminal_state must work via JobManager.get_job(), not provider._jobs._store."""
    from quodeq.api._log_stream_routes import _stream_terminal_state
    from quodeq.core.types.job import JobSnapshot

    class FakeJobs:
        def get_job(self, job_id):
            return JobSnapshot(job_id=job_id, status="done", output_project=None)
        # Deliberately no _store attribute — proves the route doesn't reach for it.

    class FakeProvider:
        _jobs = FakeJobs()

        def get_log_run_dir(self, job_id):
            return None

    assert _stream_terminal_state(FakeProvider(), "job-1") == "done"


def test_is_preparing_job_treats_lost_as_still_live(tmp_path):
    """A LOST job's tracking thread died, but the subprocess may still be
    running -- _is_preparing_job must not treat it as finished (JOB_FINISHED
    excludes LOST on purpose)."""
    from quodeq.api._log_stream_routes import _is_preparing_job
    from quodeq.core.types.job import JobSnapshot

    class FakeJobs:
        def get_job(self, job_id):
            return JobSnapshot(job_id=job_id, status="lost", output_project=None)

    class FakeProvider:
        _jobs = FakeJobs()

    assert _is_preparing_job(FakeProvider(), "job-1") is True


def test_stream_terminal_state_falls_through_to_status_json_for_lost_job(tmp_path):
    """A LOST job must not short-circuit to "lost" -- it falls through to
    status.json's real state, same as before JobStatus existed."""
    from quodeq.api._log_stream_routes import _stream_terminal_state
    from quodeq.core.types.job import JobSnapshot
    import json

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "status.json").write_text(json.dumps({"state": "running"}), encoding="utf-8")

    class FakeJobs:
        def get_job(self, job_id):
            return JobSnapshot(job_id=job_id, status="lost", output_project=None)

    class FakeProvider:
        _jobs = FakeJobs()

        def get_log_run_dir(self, job_id):
            return run_dir

    assert _stream_terminal_state(FakeProvider(), "job-1") == "running"
