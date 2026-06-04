import json
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload, EventType
from quodeq.core.events.writer import EventLogWriter


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def writer(log_path: Path) -> EventLogWriter:
    return EventLogWriter(log_path)


def test_emit_judgment_event(writer: EventLogWriter, log_path: Path):
    payload = JudgmentPayload(
        practice_id="clean-arch-001",
        verdict="violation",
        dimension="Security",
        file="src/auth.py",
        line=42,
        reason="Hardcoded secret detected",
        title="Hardcoded Secret",
        confidence=95
    )
    event = JudgmentCreatedEvent(payload=payload)
    writer.emit(event)

    assert log_path.exists()
    assert log_path.stat().st_size > 0

    with open(log_path, "r") as f:
        data = json.loads(f.readline())

    assert data["event_type"] == EventType.JUDGMENT_CREATED
    assert data["payload"]["practice_id"] == "clean-arch-001"
    assert data["payload"]["verdict"] == "violation"
    assert data["payload"]["line"] == 42
    assert "event_id" in data
    assert "timestamp" in data


def test_multiple_events_append(writer: EventLogWriter, log_path: Path):
    payload1 = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    payload2 = JudgmentPayload(practice_id="p2", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")

    writer.emit(JudgmentCreatedEvent(payload=payload1))
    writer.emit(JudgmentCreatedEvent(payload=payload2))

    with open(log_path, "r") as f:
        lines = f.readlines()

    assert len(lines) == 2
    assert "p1" in lines[0]
    assert "p2" in lines[1]


def test_judgment_payload_accepts_req_field():
    p = JudgmentPayload(
        practice_id="M-ANA",
        verdict="violation",
        dimension="maintainability",
        file="foo.py",
        line=1,
        reason="too long",
        req="R-ANA-1",
    )
    assert p.req == "R-ANA-1"


def test_judgment_payload_req_defaults_to_none():
    p = JudgmentPayload(
        practice_id="M-ANA",
        verdict="violation",
        dimension="maintainability",
        file="foo.py",
        line=1,
        reason="too long",
    )
    assert p.req is None
