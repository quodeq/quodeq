from __future__ import annotations

import json

from quodeq.core.events.models import (
    EVENT_MODEL_MAP,
    EventType,
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.data.events.codec import event_to_json


def test_finding_dismissed_payload_required_fields():
    payload = FindingDismissed(req="R1", file="a.py", line=10)
    assert payload.req == "R1"
    assert payload.file == "a.py"
    assert payload.line == 10
    assert payload.reason is None


def test_finding_dismissed_payload_optional_reason():
    payload = FindingDismissed(req="R1", file="a.py", line=10, reason="false positive")
    assert payload.reason == "false positive"


def test_finding_dismissed_event_type_is_set():
    event = FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    assert event.event_type == EventType.FINDING_DISMISSED


def test_finding_undismissed_event_type_is_set():
    event = FindingUndismissedEvent(payload=FindingUndismissed(req="R1", file="a.py", line=10))
    assert event.event_type == EventType.FINDING_UNDISMISSED


def test_event_model_map_includes_new_events():
    assert EVENT_MODEL_MAP[EventType.FINDING_DISMISSED] is FindingDismissedEvent
    assert EVENT_MODEL_MAP[EventType.FINDING_UNDISMISSED] is FindingUndismissedEvent


def test_finding_dismissed_event_round_trips_through_json():
    event = FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10, reason="x"))
    line = event_to_json(event)
    data = json.loads(line)
    assert data["event_type"] == "FINDING_DISMISSED"
    assert data["payload"]["req"] == "R1"
    assert data["payload"]["reason"] == "x"
    assert data["payload"]["fingerprint"] is None


def test_fingerprint_round_trips_and_legacy_lines_decode_without_it():
    from quodeq.data.events.codec import event_from_dict

    event = FindingDismissedEvent(payload=FindingDismissed(
        req="R1", file="a.py", line=10, fingerprint="ab" * 32))
    decoded = event_from_dict(FindingDismissedEvent, json.loads(event_to_json(event)))
    assert decoded.payload.fingerprint == "ab" * 32

    legacy = {
        "event_id": str(event.event_id), "timestamp": "2026-07-24T10:00:00Z",
        "event_type": "FINDING_UNDISMISSED",
        "payload": {"req": "R1", "file": "a.py", "line": 10},
    }
    assert event_from_dict(FindingUndismissedEvent, legacy).payload.fingerprint is None
