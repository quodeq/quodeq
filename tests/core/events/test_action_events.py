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
    line = event.model_dump_json()
    data = json.loads(line)
    assert data["event_type"] == "FINDING_DISMISSED"
    assert data["payload"]["req"] == "R1"
    assert data["payload"]["reason"] == "x"
