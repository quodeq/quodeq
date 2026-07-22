import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.reader import EventLogReader
from quodeq.core.events.writer import EventLogWriter


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def writer(log_path: Path) -> EventLogWriter:
    return EventLogWriter(log_path)


@pytest.fixture
def reader(log_path: Path) -> EventLogReader:
    return EventLogReader(log_path)


def test_stream_and_checkpoint(writer: EventLogWriter, reader: EventLogReader):
    payload1 = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    event1 = JudgmentCreatedEvent(payload=payload1)
    writer.emit(event1)

    ts_checkpoint = event1.timestamp

    time.sleep(0.1)

    payload2 = JudgmentPayload(practice_id="p2", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")
    event2 = JudgmentCreatedEvent(payload=payload2)
    writer.emit(event2)

    all_events = list(reader.stream())
    assert len(all_events) == 2

    filtered_events = list(reader.stream(since_timestamp=ts_checkpoint))
    assert len(filtered_events) == 1
    assert filtered_events[0].payload.practice_id == "p2"


def test_resilience_to_corruption(writer: EventLogWriter, reader: EventLogReader, log_path: Path):
    payload = JudgmentPayload(practice_id="good", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    writer.emit(JudgmentCreatedEvent(payload=payload))

    with open(log_path, "a") as f:
        f.write("NOT_A_JSON_LINE\n")
        f.write('{"event_type": "INVALID_TYPE", "payload": {}}\n')
        f.write('{"event_id": "not-a-uuid", "event_type": "JUDGMENT_CREATED", "payload": {}}\n')

    payload2 = JudgmentPayload(practice_id="after_corruption", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")
    writer.emit(JudgmentCreatedEvent(payload=payload2))

    events = list(reader.stream())
    assert len(events) == 2
    assert events[0].payload.practice_id == "good"
    assert events[1].payload.practice_id == "after_corruption"


def test_malformed_json_hits_json_specific_handler(
    writer: EventLogWriter, reader: EventLogReader, log_path: Path, caplog,
):
    """Regression: json.JSONDecodeError subclasses ValueError, so the JSON
    branch must come first or malformed JSON is logged as 'Invalid event
    structure' instead of 'Malformed JSON'."""
    with open(log_path, "a") as f:
        f.write("NOT_A_JSON_LINE\n")

    with caplog.at_level("ERROR"):
        assert list(reader.stream()) == []

    assert any("Malformed JSON" in r.message for r in caplog.records)
    assert not any("Invalid event structure" in r.message for r in caplog.records)


def test_latest_timestamp(writer: EventLogWriter, reader: EventLogReader):
    payload = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    writer.emit(JudgmentCreatedEvent(payload=payload))

    latest = reader.get_latest_timestamp()
    assert latest is not None
    assert isinstance(latest, datetime)
