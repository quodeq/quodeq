import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events import reader as reader_module
from quodeq.data.events.reader import EventLogReader
from quodeq.data.events.writer import EventLogWriter


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


def test_latest_timestamp_missing_file_is_caught(tmp_path: Path):
    """get_latest_timestamp's except was narrowed
    from bare `Exception` to `(OSError, UnicodeDecodeError)` (R-FT-7). A missing log
    file (open() raising FileNotFoundError, an OSError subclass) is the
    realistic case this function exists to tolerate: return None, not raise."""
    missing = tmp_path / "does-not-exist.jsonl"
    reader = EventLogReader(missing)

    assert reader.get_latest_timestamp() is None


def test_latest_timestamp_undecodable_bytes_are_caught(log_path: Path, reader: EventLogReader):
    """A log corrupted with invalid UTF-8 raises UnicodeDecodeError during
    line iteration (not just at open()) -- also part of the realistic
    surface, per load_index's precedent of bundling I/O-open failures with
    decode failures."""
    with open(log_path, "wb") as f:
        f.write(b'{"event_type": "JUDGMENT_CREATED"}\n')
        f.write(b"\xff\xfe not valid utf-8\n")

    assert reader.get_latest_timestamp() is None


def test_latest_timestamp_out_of_scope_error_propagates(
    writer: EventLogWriter, reader: EventLogReader, monkeypatch,
):
    """R-FT-7 — an error outside (OSError, UnicodeDecodeError) (e.g. a
    programming bug in the streaming pipeline) must now propagate instead
    of being swallowed and reported as 'no timestamp found'."""
    payload = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    writer.emit(JudgmentCreatedEvent(payload=payload))

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover - makes this a generator, never reached

    monkeypatch.setattr(reader, "stream", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        reader.get_latest_timestamp()


def test_non_object_json_lines_are_skipped(
    writer: EventLogWriter, reader: EventLogReader, log_path: Path,
):
    """A list, null or bare string is valid JSON but not an event object.
    Each must be skipped like any other malformed line, not raise."""
    payload = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    writer.emit(JudgmentCreatedEvent(payload=payload))

    with open(log_path, "a") as f:
        f.write("[1]\n")
        f.write("null\n")
        f.write('"x"\n')

    events = list(reader.stream())
    assert len(events) == 1
    assert events[0].payload.practice_id == "p1"


def test_naive_timestamp_against_aware_since_is_skipped_not_raised(
    log_path: Path, reader: EventLogReader,
):
    """A stored event with a naive timestamp compared against an aware
    since_timestamp raises TypeError from the ``<=`` comparison. That
    TypeError is part of the narrow handler's realistic surface, so the
    line is skipped, not propagated."""
    raw_line = json.dumps({
        "event_type": "JUDGMENT_CREATED",
        "timestamp": "2024-01-01T00:00:00",
        "payload": {
            "practice_id": "p1", "verdict": "compliance", "dimension": "D1",
            "file": "f1", "line": 1, "reason": "r1",
        },
    })
    log_path.write_text(raw_line + "\n", encoding="utf-8")

    since = datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert list(reader.stream(since_timestamp=since)) == []


def test_runtime_error_propagates_narrow_handler(
    writer: EventLogWriter, reader: EventLogReader, monkeypatch,
):
    """R-FT-7: the per-line handler is narrow. An error outside its declared
    exceptions (e.g. a programming bug inside event_from_dict) must
    propagate out of stream(), not be swallowed and logged as a skip."""
    payload = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    writer.emit(JudgmentCreatedEvent(payload=payload))

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(reader_module, "event_from_dict", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        list(reader.stream())
