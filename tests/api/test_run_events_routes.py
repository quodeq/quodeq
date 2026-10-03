"""Flask test client coverage for /api/evaluations/<jobId>/events."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from quodeq.api._run_events_routes import register_run_events_routes
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services.jobs import JobManager


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    provider = MagicMock()
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    provider.get_log_run_dir = lambda job_id: run_dir if job_id == "job-1" else None
    provider.in_memory_job = lambda _job_id: None
    app.config["_provider"] = provider
    app.config["_run_dir"] = run_dir
    register_run_events_routes(app)
    return app


def _write_finding(
    event_log: EventLogWriter, p: str, line: int = 1, *, verdict: str = "violation",
) -> None:
    payload = JudgmentPayload(
        practice_id=p, verdict=verdict, dimension="dim",
        file="x.py", line=line, reason="r", severity="medium", snippet="s", title="t",
    )
    event_log.emit(JudgmentCreatedEvent(payload=payload))


def _finding_frames(body: str) -> list[dict]:
    blocks = [b for b in body.split("\n\n") if "event: finding" in b]
    return [
        json.loads(next(l for l in b.splitlines() if l.startswith("data: "))[len("data: "):])
        for b in blocks
    ]


def test_route_returns_404_for_unknown_job(app: Flask):
    client = app.test_client()
    resp = client.get("/api/evaluations/bogus/events")
    assert resp.status_code in (404, 410)


def test_unresolvable_job_reports_gone_code_not_not_found(app: Flask):
    """job_id resolves to no run dir -> 410, and the JSON
    ``code`` field must say GONE, not the hardcoded NOT_FOUND that used
    to be returned regardless of the actual HTTP status."""
    client = app.test_client()
    resp = client.get("/api/evaluations/bogus/events")
    assert resp.status_code == 410
    assert resp.get_json()["code"] == "GONE"


def test_unsupported_provider_reports_not_found_code():
    """A provider that doesn't implement get_log_run_dir at all is a
    different failure than a cleaned-up run -- code stays NOT_FOUND."""
    bare_app = Flask(__name__)
    bare_app.config["_provider"] = object()
    register_run_events_routes(bare_app)
    resp = bare_app.test_client().get("/api/evaluations/job-1/events")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NOT_FOUND"


def test_route_returns_text_event_stream(app: Flask):
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    client = app.test_client()
    resp = client.get("/api/evaluations/job-1/events")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.headers.get("Cache-Control") == "no-cache"


def test_route_emits_status_event_for_running_run(app: Flask, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    client = app.test_client()
    resp = client.get("/api/evaluations/job-1/events")
    body = resp.get_data(as_text=True)
    assert "event: status" in body
    assert "event: done" in body


def test_route_honors_last_event_id_header(app: Flask, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    event_log = EventLogWriter(run_dir / "events.jsonl")
    _write_finding(event_log, "P1", line=1)
    _write_finding(event_log, "P2", line=2)

    # First request: get all findings and capture the timestamp of finding #1
    client = app.test_client()
    resp0 = client.get("/api/evaluations/job-1/events")
    body0 = resp0.get_data(as_text=True)
    finding_blocks = [b for b in body0.split("\n\n") if "event: finding" in b]
    assert len(finding_blocks) == 2
    # Extract the SSE id: line (ISO timestamp) from finding #1's block
    ts_of_first = next(
        line[len("id: "):] for line in finding_blocks[0].splitlines() if line.startswith("id: ")
    )

    # Reconnect after finding #1's timestamp → should get only finding #2
    resp = client.get("/api/evaluations/job-1/events", headers={"Last-Event-ID": ts_of_first})
    body = resp.get_data(as_text=True)
    finding_lines = [b for b in body.split("\n\n") if "event: finding" in b]
    assert len(finding_lines) == 1
    data = json.loads(next(l for l in finding_lines[0].splitlines() if l.startswith("data: "))[6:])
    assert data["practice_id"] == "P2"


def test_route_does_not_emit_a_compliance_judgment_as_a_finding(app: Flask, monkeypatch: pytest.MonkeyPatch):
    """events.jsonl holds every judgment, passing checks included. The feed
    used to show them all as violations (42 in the report, 417 on screen)."""
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    event_log = EventLogWriter(run_dir / "events.jsonl")
    _write_finding(event_log, "P1", line=1, verdict="compliance")
    _write_finding(event_log, "P2", line=2)
    body = app.test_client().get("/api/evaluations/job-1/events").get_data(as_text=True)
    assert [f["practice_id"] for f in _finding_frames(body)] == ["P2"]


def test_route_emits_a_finding_reported_twice_once(app: Flask, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    event_log = EventLogWriter(run_dir / "events.jsonl")
    _write_finding(event_log, "P1", line=1)
    _write_finding(event_log, "P1", line=1)
    body = app.test_client().get("/api/evaluations/job-1/events").get_data(as_text=True)
    assert len(_finding_frames(body)) == 1


# ---------------------------------------------------------------------------
# #14 -- path traversal via job_id in get_log_run_dir filesystem scan
# ---------------------------------------------------------------------------

def test_get_log_run_dir_rejects_traversal_in_run_id(tmp_path: Path):
    """A job_id containing '..' must not resolve to a directory outside reports_root."""
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    project_dir = reports_root / "my-project"
    project_dir.mkdir()

    # Create a directory *outside* reports_root that the traversal would escape to
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    # Craft a run_id that, when appended to project_dir, traverses outside reports_root:
    # project_dir / "../../outside" resolves to tmp_path / "outside"
    traversal_job_id = "../../outside"

    index = EvaluationsIndex(
        jobs=JobManager(),
        reports_root=reports_root,
    )
    result = index.get_log_run_dir(traversal_job_id)
    # The result must not be outside reports_root (use resolve() for canonical comparison)
    outside_resolved = outside_dir.resolve()
    reports_resolved = reports_root.resolve()
    assert result is None or (
        result.resolve() != outside_resolved
        and result.resolve().is_relative_to(reports_resolved)
    )


# ---------------------------------------------------------------------------
# Preparing window: the run dir does not exist yet when the UI opens the stream
# ---------------------------------------------------------------------------

class _FakeJob:
    def __init__(self, status: str = "running") -> None:
        self.status = status


def _preparing_provider(tmp_path: Path):
    """A provider whose job is running but has no run dir on the first lookup.

    The second ``get_log_run_dir`` call creates and returns the run dir with
    a terminal status.json, the way the runner's report_path marker lands a
    moment after the UI opened the stream.
    """
    provider = MagicMock()
    run_dir = tmp_path / "late-run"
    job = _FakeJob()
    calls = [0]

    def get_log_run_dir(_job_id):
        calls[0] += 1
        if calls[0] == 1:
            return None
        if not run_dir.is_dir():
            run_dir.mkdir()
            (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
            event_log = EventLogWriter(run_dir / "events.jsonl")
            _write_finding(event_log, "P1", line=1)
        return run_dir

    provider.get_log_run_dir = get_log_run_dir
    provider.in_memory_job = lambda _job_id: job
    provider.is_job_complete = lambda _job_id: job.status == "done"
    return provider, job


def test_route_waits_for_preparing_job_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A running job with no run dir yet must get a 200 event-stream, not a
    410: a non-200 closes the browser's EventSource for good and the
    Evaluate screen then never shows a live finding for that run."""
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    app = Flask(__name__)
    provider, _job = _preparing_provider(tmp_path)
    app.config["_provider"] = provider
    register_run_events_routes(app)

    resp = app.test_client().get("/api/evaluations/job-late/events")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    body = resp.get_data(as_text=True)
    assert "event: finding" in body
    assert "event: status" in body
    assert "event: done" in body


def test_route_closes_when_preparing_job_ends_without_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A job that fails before creating its run dir must end the stream with
    ``event: done`` instead of holding the connection open."""
    monkeypatch.setenv("QUODEQ_SSE_TICK_MS", "0")
    app = Flask(__name__)
    provider = MagicMock()
    job = _FakeJob()
    provider.get_log_run_dir = lambda _job_id: None
    provider.in_memory_job = lambda _job_id: job
    calls = [0]

    def is_job_complete(_job_id):
        calls[0] += 1
        job.status = "failed"
        return True

    provider.is_job_complete = is_job_complete
    app.config["_provider"] = provider
    register_run_events_routes(app)

    resp = app.test_client().get("/api/evaluations/job-dead/events")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "event: done" in body
    assert "event: finding" not in body


def test_route_still_rejects_unknown_job_when_nothing_is_running(tmp_path: Path):
    app = Flask(__name__)
    provider = MagicMock()
    provider.get_log_run_dir = lambda _job_id: None
    provider.in_memory_job = lambda _job_id: None
    app.config["_provider"] = provider
    register_run_events_routes(app)
    resp = app.test_client().get("/api/evaluations/bogus/events")
    assert resp.status_code == 410
