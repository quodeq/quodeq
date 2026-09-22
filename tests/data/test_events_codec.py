"""Wire-format contract for the event codec in data.events.codec.

The event entities are plain dataclasses; the codec owns their JSON shape.
Existing events.jsonl files were written by the previous pydantic-based
serializer, so decoding must stay byte-for-byte compatible: legacy
bare-string req_refs coerce to ReqRef, unknown keys are ignored, and writer
output round-trips through the reader unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import (
    EventType,
    Judgment,
    JudgmentCreatedEvent,
)
from quodeq.core.types.req_ref import ReqRef
from quodeq.data.events.codec import event_from_dict, event_to_json
from quodeq.data.events.reader import EventLogReader
from quodeq.data.events.writer import EventLogWriter


# Verbatim shape of a pre-ReqRef-struct events.jsonl line: req_refs is a
# list of bare strings, timestamp carries the "+00:00" pydantic offset form.
_LEGACY_LINE = json.dumps({
    "event_id": "00000000-0000-0000-0000-000000000042",
    "timestamp": "2025-11-03T08:15:00+00:00",
    "event_type": "JUDGMENT_CREATED",
    "payload": {
        "practice_id": "Integrity",
        "verdict": "violation",
        "dimension": "security",
        "file": "auth.py",
        "line": 10,
        "reason": "weak hash",
        "severity": "major",
        "req": "Integrity.MD5",
        "req_refs": ["CWE-327", "CISQ"],
    },
})


def test_old_format_line_decodes_through_reader_with_coerced_req_refs(tmp_path: Path):
    log_path = tmp_path / "events.jsonl"
    log_path.write_text(_LEGACY_LINE + "\n", encoding="utf-8")

    events = EventLogReader(log_path).read_all()

    assert len(events) == 1
    refs = events[0].payload.req_refs
    assert refs == [ReqRef(label="CWE-327", url=""), ReqRef(label="CISQ", url="")]


def test_writer_output_round_trips_through_reader(tmp_path: Path):
    payload = Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="src/auth.py", line=42, end_line=44, reason="hardcoded secret",
        severity="high", title="Hardcoded secret", confidence=95,
        req="SEC-1", req_refs=[ReqRef(label="CWE-798", url="https://cwe.mitre.org/798")],
        scope_downgrade={"rule": "internal-tool", "from": "major", "to": "minor"},
    )
    event = JudgmentCreatedEvent(payload=payload)
    log_path = tmp_path / "events.jsonl"
    EventLogWriter(log_path).emit(event)

    events = EventLogReader(log_path).read_all()

    assert len(events) == 1
    assert events[0] == event  # payload fields, event_id and timestamp all equal


def test_unknown_keys_are_ignored_not_fatal():
    raw = json.loads(_LEGACY_LINE)
    raw["schema_version"] = 3  # unknown envelope key
    raw["payload"]["novel_marker"] = True  # unknown payload key

    event = event_from_dict(JudgmentCreatedEvent, raw)

    assert event.event_type is EventType.JUDGMENT_CREATED
    assert event.payload.practice_id == "Integrity"
    assert not hasattr(event.payload, "novel_marker")


def test_utc_timestamp_serializes_with_trailing_z_and_parses_back():
    event = JudgmentCreatedEvent(payload=Judgment(
        practice_id="P1", verdict="compliance", dimension="D",
        file="a.py", line=1, reason="ok",
    ))
    data = json.loads(event_to_json(event))

    assert data["timestamp"].endswith("Z")  # pydantic v2 wire form, kept
    decoded = event_from_dict(JudgmentCreatedEvent, data)
    assert decoded.timestamp == event.timestamp
