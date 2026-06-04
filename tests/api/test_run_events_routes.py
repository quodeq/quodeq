"""Flask test client coverage for /api/evaluations/<jobId>/events."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from quodeq.api._run_events_routes import register_run_events_routes
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    provider = MagicMock()
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    provider.get_log_run_dir = lambda job_id: run_dir if job_id == "job-1" else None
    app.config["_provider"] = provider
    app.config["_run_dir"] = run_dir
    register_run_events_routes(app)
    return app


def _write_finding(event_log: EventLogWriter, p: str, line: int = 1) -> None:
    payload = JudgmentPayload(
        practice_id=p, verdict="violation", dimension="dim",
        file="x.py", line=line, reason="r", severity="medium", snippet="s", title="t",
    )
    event_log.emit(JudgmentCreatedEvent(payload=payload))


def test_route_returns_404_for_unknown_job(app: Flask):
    client = app.test_client()
    resp = client.get("/api/evaluations/bogus/events")
    assert resp.status_code in (404, 410)


def test_route_returns_text_event_stream(app: Flask):
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    client = app.test_client()
    resp = client.get("/api/evaluations/job-1/events")
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.headers.get("Cache-Control") == "no-cache"


def test_route_emits_status_event_for_running_run(app: Flask):
    import os
    os.environ["QUODEQ_SSE_TICK_MS"] = "0"
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))
    client = app.test_client()
    resp = client.get("/api/evaluations/job-1/events")
    body = resp.get_data(as_text=True)
    assert "event: status" in body
    assert "event: done" in body


def test_route_honors_last_event_id_header(app: Flask):
    import os
    os.environ["QUODEQ_SSE_TICK_MS"] = "0"
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
