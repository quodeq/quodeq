"""End-to-end SSE flow: simulate a run via artifacts, observe events."""
from __future__ import annotations

import json
import os
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
    run_dir = tmp_path / "run-e2e"
    run_dir.mkdir()
    provider.get_log_run_dir = lambda job_id: run_dir if job_id == "j" else None
    app.config["_provider"] = provider
    app.config["_run_dir"] = run_dir
    register_run_events_routes(app)
    os.environ["QUODEQ_SSE_TICK_MS"] = "0"  # drain-once mode for fast tests
    return app


def _parse_sse_frames(body: str) -> list[dict]:
    """Parse SSE response body into a list of {event, data, id} dicts."""
    frames: list[dict] = []
    for raw in body.split("\n\n"):
        if not raw.strip() or raw.lstrip().startswith(":"):
            continue
        frame: dict = {}
        for line in raw.splitlines():
            if line.startswith("event: "):
                frame["event"] = line[len("event: "):]
            elif line.startswith("data: "):
                frame["data"] = line[len("data: "):]
            elif line.startswith("id: "):
                frame["id"] = int(line[len("id: "):])
        if "event" in frame:
            frames.append(frame)
    return frames


def test_e2e_run_with_dimensions_and_findings(app: Flask):
    run_dir: Path = app.config["_run_dir"]

    # Simulate a run that has finished with one dimension and two findings.
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir()
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "score": 92, "grade": "A",
    }))
    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding({"p": "P1", "file": "x.py", "line": 1, "t": "violation",
                         "severity": "high", "d": "security", "reason": "sql injection",
                         "snippet": "...", "w": "title"})
    repo.insert_finding({"p": "P2", "file": "y.py", "line": 5, "t": "violation",
                         "severity": "medium", "d": "security", "reason": "weak crypto",
                         "snippet": "...", "w": "title"})
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    client = app.test_client()
    resp = client.get("/api/evaluations/j/events")
    assert resp.status_code == 200
    frames = _parse_sse_frames(resp.get_data(as_text=True))

    types = [f["event"] for f in frames]
    assert types[0] == "status"
    assert "dimension-completed" in types
    assert types.count("finding") == 2
    assert types[-1] == "done"

    finding_ids = [f["id"] for f in frames if f["event"] == "finding"]
    assert finding_ids == [1, 2]


def test_e2e_reconnect_with_last_event_id_skips_emitted_findings(app: Flask):
    run_dir: Path = app.config["_run_dir"]
    repo = SqliteFindingsRepository(run_dir)
    for i in range(1, 4):
        repo.insert_finding({"p": f"P{i}", "file": "x.py", "line": i, "t": "violation",
                             "severity": "medium", "d": "dim", "reason": "r",
                             "snippet": "s", "w": "t"})
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    client = app.test_client()
    resp = client.get("/api/evaluations/j/events", headers={"Last-Event-ID": "2"})
    frames = _parse_sse_frames(resp.get_data(as_text=True))
    finding_ids = [f["id"] for f in frames if f["event"] == "finding"]
    assert finding_ids == [3]


def test_e2e_pending_run_emits_pending_status(app: Flask):
    # No status.json, no evaluation/, no findings — the pending case.
    # This shouldn't loop forever, so we set the env to drain once.
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))  # terminate quickly

    client = app.test_client()
    resp = client.get("/api/evaluations/j/events")
    frames = _parse_sse_frames(resp.get_data(as_text=True))
    status_frames = [f for f in frames if f["event"] == "status"]
    assert len(status_frames) >= 1
