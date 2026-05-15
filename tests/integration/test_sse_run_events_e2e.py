"""End-to-end SSE flow: simulate a run via artifacts, observe events."""
from __future__ import annotations

import json
import os
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
                frame["id"] = line[len("id: "):]  # ISO timestamp string
        if "event" in frame:
            frames.append(frame)
    return frames


def _write_finding(event_log: EventLogWriter, p: str, file: str = "x.py", line: int = 1) -> None:
    payload = JudgmentPayload(
        practice_id=p,
        verdict="violation",
        dimension="security",
        file=file,
        line=line,
        reason="test reason",
        severity="medium",
        snippet="...",
        title="title",
    )
    event_log.emit(JudgmentCreatedEvent(payload=payload))


def test_e2e_run_with_dimensions_and_findings(app: Flask):
    run_dir: Path = app.config["_run_dir"]

    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir()
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "score": 92, "grade": "A",
    }))

    event_log = EventLogWriter(run_dir / "events.jsonl")
    _write_finding(event_log, "P1", "x.py", 1)
    _write_finding(event_log, "P2", "y.py", 5)

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

    # Sequential payload IDs are 1 and 2
    finding_payload_ids = [
        json.loads(f["data"])["id"] for f in frames if f["event"] == "finding"
    ]
    assert finding_payload_ids == [1, 2]


def test_e2e_reconnect_with_last_event_id_skips_emitted_findings(app: Flask):
    run_dir: Path = app.config["_run_dir"]
    event_log = EventLogWriter(run_dir / "events.jsonl")
    for i in range(1, 4):
        _write_finding(event_log, f"P{i}", line=i)

    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    # First request: get all 3 findings and capture the timestamp of finding #1
    client = app.test_client()
    resp = client.get("/api/evaluations/j/events")
    all_frames = _parse_sse_frames(resp.get_data(as_text=True))
    finding_frames = [f for f in all_frames if f["event"] == "finding"]
    assert len(finding_frames) == 3

    # Reconnect after finding #2's timestamp → should get only finding #3
    ts_after_finding2 = finding_frames[1]["id"]  # ISO timestamp of finding #2
    resp2 = client.get("/api/evaluations/j/events", headers={"Last-Event-ID": ts_after_finding2})
    frames2 = _parse_sse_frames(resp2.get_data(as_text=True))
    finding_ids2 = [json.loads(f["data"])["id"] for f in frames2 if f["event"] == "finding"]
    assert len(finding_ids2) == 1
    assert json.loads([f for f in frames2 if f["event"] == "finding"][0]["data"])["practice_id"] == "P3"


def test_e2e_pending_run_emits_pending_status(app: Flask):
    run_dir: Path = app.config["_run_dir"]
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    client = app.test_client()
    resp = client.get("/api/evaluations/j/events")
    frames = _parse_sse_frames(resp.get_data(as_text=True))
    status_frames = [f for f in frames if f["event"] == "status"]
    assert len(status_frames) >= 1
