"""Tests for GET /api/jobs/<id>/logs/stream (SSE live tail)."""
from __future__ import annotations

from http import HTTPStatus

from tests.api._log_stream_routes_fixtures import (  # noqa: F401 -- app is a pytest fixture
    _collect_sse,
    _seed_run,
    app,
)


def test_sse_replays_existing_content(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-sse-1-done", "alpha\nbeta\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-1-done/logs/stream")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith("text/event-stream")
    events = _collect_sse(resp)
    # `done` events also carry a `data:` line (the terminal state); filter
    # them out when asserting on the streamed log lines.
    line_events = [e for e in events if "data" in e and e.get("event") != "done"]
    assert [e["data"] for e in line_events] == ["alpha", "beta"]
    assert any(e.get("event") == "done" for e in events)


def test_sse_respects_last_event_id(tmp_path, app) -> None:
    _seed_run(tmp_path, app, "job-sse-2-done", "alpha\nbeta\ngamma\n")
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-2-done/logs/stream",
                      headers={"Last-Event-ID": str(len("alpha\n"))})
    events = _collect_sse(resp)
    line_events = [e for e in events if "data" in e and e.get("event") != "done"]
    assert [e["data"] for e in line_events] == ["beta", "gamma"]


def test_sse_waits_when_run_log_missing_then_emits_done(tmp_path, app) -> None:
    """run_dir exists, run.log doesn't — the job is still preparing.

    The stream must not 404 (which would close the EventSource and leave
    the dashboard's console pane showing "stream disconnected" forever).
    Instead it stays open and emits ``event: done`` once the job ends.
    """
    run_dir = tmp_path / "empty"
    run_dir.mkdir()
    # The fake provider's is_job_complete returns True for ids ending in
    # "-done", so the generator terminates on the first iteration.
    app.config["_provider"].map["job-prep-done"] = run_dir
    client = app.test_client()
    resp = client.get("/api/jobs/job-prep-done/logs/stream")
    assert resp.status_code == HTTPStatus.OK
    assert resp.content_type.startswith("text/event-stream")
    events = _collect_sse(resp)
    line_events = [e for e in events if "data" in e and e.get("event") != "done"]
    assert line_events == []
    assert any(e.get("event") == "done" for e in events)


def test_sse_410_for_unknown_job(tmp_path, app) -> None:
    """A jobId the provider can't resolve and that JobManager doesn't know
    about must still be rejected — we don't want a typo'd id to pin a
    polling thread open indefinitely."""
    client = app.test_client()
    resp = client.get("/api/jobs/job-unknown/logs/stream")
    assert resp.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE)


def test_sse_waits_for_preparing_internal_job(tmp_path, app) -> None:
    """Internal jobs registered with JobManager have no run_dir until the
    runner emits the report_path marker. The SSE stream stays open
    during that preparing window even though get_log_run_dir returns
    None, and emits ``event: done`` when the in-memory job flips to a
    terminal state."""
    class FakeJob:
        def __init__(self, status: str) -> None:
            self.status = status

    class JobsHolder:
        def __init__(self, job: FakeJob) -> None:
            self._job = job

        def get_job(self, _job_id: str) -> FakeJob:
            return self._job

    job = FakeJob("running")
    provider = app.config["_provider"]
    provider.in_memory_job = JobsHolder(job).get_job

    # Flip the job to "done" on the second is_job_complete call so the
    # generator first sees an active preparing job (path None, not done)
    # and on the next tick gets the done frame.
    calls = [0]
    original_is_done = provider.is_job_complete

    def is_done(job_id: str) -> bool:
        calls[0] += 1
        if calls[0] >= 2:
            job.status = "done"
            return True
        return original_is_done(job_id)

    provider.is_job_complete = is_done

    client = app.test_client()
    resp = client.get("/api/jobs/internal-prep/logs/stream")
    assert resp.status_code == HTTPStatus.OK
    events = _collect_sse(resp)
    assert any(e.get("event") == "done" for e in events)


def test_sse_streams_log_after_it_appears(tmp_path, app) -> None:
    """When run.log materializes mid-stream (the runner finally emitted
    the report_path marker and JobManager flushed the buffered preparing
    output), the generator picks it up and emits the lines."""
    run_dir = tmp_path / "appears"
    run_dir.mkdir()
    log_path = run_dir / "run.log"

    # Job is in JobManager's in-memory store so _is_preparing_job
    # accepts the request even though get_log_run_dir initially says
    # "no run dir yet" (mirrors the pre-marker reality).
    class FakeJob:
        status = "running"

    class JobsHolder:
        def get_job(self, _job_id):
            return FakeJob()

    provider = app.config["_provider"]
    provider.in_memory_job = JobsHolder().get_job

    # First call (from the route's resolve_run_log) returns None, so
    # the route falls through to _is_preparing_job and opens the SSE
    # response. From the second call onward (generator's lazy resolver)
    # the run dir is "available" and run.log gets seeded — that's the
    # exact moment the dashboard's preparing burst arrives in real life.
    calls = [0]

    def get_log_run_dir(_job_id):
        calls[0] += 1
        if calls[0] == 1:
            return None
        if calls[0] == 2:
            log_path.write_text("preparing-line-1\npreparing-line-2\n")
        return run_dir

    provider.get_log_run_dir = get_log_run_dir

    client = app.test_client()
    resp = client.get("/api/jobs/job-appears-done/logs/stream")
    assert resp.status_code == HTTPStatus.OK
    events = _collect_sse(resp)
    line_events = [e for e in events if "data" in e and e.get("event") != "done"]
    assert [e["data"] for e in line_events] == ["preparing-line-1", "preparing-line-2"]
    assert any(e.get("event") == "done" for e in events)


def test_sse_filters_resources_lines(tmp_path, app) -> None:
    content = (
        "[INFO] [security] 0m10s | running\n"
        "[INFO] [resources] elapsed=1m00s rss=120MB threads=5 fds=8 ollama=200MB\n"
        "[INFO] [security] 0m20s | running\n"
    )
    _seed_run(tmp_path, app, "job-sse-filter-done", content)
    client = app.test_client()
    resp = client.get("/api/jobs/job-sse-filter-done/logs/stream")
    events = _collect_sse(resp)
    payloads = [e["data"] for e in events if "data" in e]
    assert all("[resources]" not in line for line in payloads)
    assert any("[security]" in line for line in payloads)
