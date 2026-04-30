"""Flask test client coverage for /api/evaluations/<jobId>/events."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flask import Flask

from quodeq.api._run_events_routes import register_run_events_routes
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    app = Flask(__name__)
    provider = MagicMock()
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    provider.get_log_run_dir = lambda job_id: run_dir if job_id == "job-1" else None
    app.config["_provider"] = provider
    app.config["_run_dir"] = run_dir  # for tests to use
    register_run_events_routes(app)
    return app


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
    os.environ["QUODEQ_SSE_TICK_MS"] = "0"  # drain immediately
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
    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding({"p": "P1", "file": "x.py", "line": 1, "t": "violation",
                         "severity": "medium", "d": "dim", "reason": "r",
                         "snippet": "s", "w": "t"})
    repo.insert_finding({"p": "P2", "file": "x.py", "line": 2, "t": "violation",
                         "severity": "medium", "d": "dim", "reason": "r",
                         "snippet": "s", "w": "t"})
    client = app.test_client()
    resp = client.get("/api/evaluations/job-1/events", headers={"Last-Event-ID": "1"})
    body = resp.get_data(as_text=True)
    finding_lines = [line for line in body.split("\n\n") if "event: finding" in line]
    assert len(finding_lines) == 1
    assert "id: 2" in finding_lines[0]
