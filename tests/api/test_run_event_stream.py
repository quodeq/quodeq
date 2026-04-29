"""Unit tests for the SSE run-event watcher and serializers."""
from __future__ import annotations

import json

from quodeq.api._run_event_stream import (
    serialize_status_event,
    serialize_dimension_event,
    serialize_finding_event,
)


def test_serialize_status_event_returns_json_payload():
    status = {"state": "running", "phase": "analyzing", "current_dimension": "timeliness"}
    payload = serialize_status_event(status)
    assert json.loads(payload) == status


def test_serialize_status_event_with_missing_keys():
    payload = serialize_status_event({"state": "pending"})
    assert json.loads(payload) == {"state": "pending"}


def test_serialize_dimension_event_with_eval_data():
    payload = serialize_dimension_event(
        dimension="security",
        eval_data={"dimension": "security", "score": 92, "grade": "A"},
    )
    parsed = json.loads(payload)
    assert parsed["dimension"] == "security"
    assert parsed["score"] == 92
    assert parsed["grade"] == "A"


def test_serialize_dimension_event_without_eval_data():
    payload = serialize_dimension_event(dimension="security", eval_data=None)
    parsed = json.loads(payload)
    assert parsed == {"dimension": "security"}


def test_serialize_finding_event_includes_judgment_fields():
    judgment_dict = {
        "id": 42,
        "practice_id": "P-TIM-1",
        "dimension": "timeliness",
        "verdict": "violation",
        "severity": "high",
        "file": "src/x.py",
        "line": 10,
        "title": "Late finalize",
        "reason": "missed deadline",
    }
    payload = serialize_finding_event(judgment_dict)
    parsed = json.loads(payload)
    assert parsed["id"] == 42
    assert parsed["practice_id"] == "P-TIM-1"
    assert parsed["verdict"] == "violation"


from quodeq.api._run_event_stream import WatcherState


def test_watcher_state_initial_defaults():
    state = WatcherState()
    assert state.last_event_id == 0
    assert state.last_status_mtime is None
    assert state.emitted_dimensions == frozenset()


def test_watcher_state_with_initial_last_event_id():
    state = WatcherState(last_event_id=42)
    assert state.last_event_id == 42


def test_watcher_state_with_emitted_dimensions():
    state = WatcherState(emitted_dimensions=frozenset({"security", "timeliness"}))
    assert "security" in state.emitted_dimensions
    assert "timeliness" in state.emitted_dimensions
