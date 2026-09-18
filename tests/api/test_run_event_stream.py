"""Unit tests for the SSE run-event serializers, WatcherState and heartbeat config."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from quodeq.api._run_event_stream import (
    WatcherState,
    _payload_as_sse_finding,
    serialize_status_event,
    serialize_dimension_event,
    serialize_finding_event,
)
from quodeq.core.events.models import Judgment


# ---------------------------------------------------------------------------
# Serializer tests (unchanged behavior)
# ---------------------------------------------------------------------------

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


def test_payload_as_sse_finding_includes_provenance_downgrade():
    # Issue #656: the live SSE finding payload lists fields explicitly, so the
    # gate's provenance_downgrade marker must be added there too.

    j = Judgment(
        practice_id="R-FT-2", verdict="violation", dimension="security",
        file="f.py", line=1, reason="r", severity="major",
        provenance_downgrade=True,
    )
    payload = _payload_as_sse_finding(j, finding_id=1)
    assert payload["provenance_downgrade"] is True


def test_payload_as_sse_finding_includes_carried_forward():
    # The live feed's carried-forward filter needs this flag on the SSE
    # path too, or every finding reads as new under VITE_USE_SSE_EVENTS.

    j = Judgment(
        practice_id="R-FT-2", verdict="violation", dimension="security",
        file="f.py", line=1, reason="r", severity="major",
        carried_forward=True,
    )
    payload = _payload_as_sse_finding(j, finding_id=1)
    assert payload["carried_forward"] is True


def test_payload_as_sse_finding_defaults_carried_forward_false():

    j = Judgment(
        practice_id="R-FT-2", verdict="violation", dimension="security",
        file="f.py", line=1, reason="r", severity="major",
    )
    payload = _payload_as_sse_finding(j, finding_id=1)
    assert payload["carried_forward"] is False


def test_payload_as_sse_finding_includes_scope_downgrade():
    # The scope gate's marker must reach the live SSE payload too, naming
    # the rule so the dashboard badge can say WHAT moved the finding, not
    # just that something did.

    j = Judgment(
        practice_id="S-AUT-3", verdict="violation", dimension="security",
        file="f.py", line=1, reason="r", severity="minor",
        scope_downgrade={"rule": "sourceless_path", "from": "major", "to": "minor"},
    )
    payload = _payload_as_sse_finding(j, finding_id=1)
    assert payload["scope_downgrade"] == {
        "rule": "sourceless_path", "from": "major", "to": "minor",
    }


def test_payload_as_sse_finding_defaults_scope_downgrade_none():

    j = Judgment(
        practice_id="R-FT-2", verdict="violation", dimension="security",
        file="f.py", line=1, reason="r", severity="major",
    )
    payload = _payload_as_sse_finding(j, finding_id=1)
    assert payload["scope_downgrade"] is None


# ---------------------------------------------------------------------------
# WatcherState tests
# ---------------------------------------------------------------------------

def test_watcher_state_initial_defaults():
    state = WatcherState()
    assert state.last_event_ts is None
    assert state.last_event_counter == 0
    assert state.last_status_mtime is None
    assert state.emitted_dimensions == frozenset()


def test_watcher_state_with_initial_last_event_ts():
    ts = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    state = WatcherState(last_event_ts=ts)
    assert state.last_event_ts == ts


def test_watcher_state_with_emitted_dimensions():
    state = WatcherState(emitted_dimensions=frozenset({"security", "timeliness"}))
    assert "security" in state.emitted_dimensions
    assert "timeliness" in state.emitted_dimensions


# ---------------------------------------------------------------------------
# REL-023 -- a malformed QUODEQ_SSE_HEARTBEAT_S must not raise at module
# import (that would prevent the API process from starting); it falls back
# to the 15s default. Out-of-range values fall back too.
# ---------------------------------------------------------------------------

def test_heartbeat_env_fallback_never_breaks_import(monkeypatch):
    import importlib

    from quodeq.api import _run_event_stream as mod

    try:
        monkeypatch.setenv("QUODEQ_SSE_HEARTBEAT_S", "not-a-number")
        assert importlib.reload(mod)._HEARTBEAT_S == 15.0

        monkeypatch.setenv("QUODEQ_SSE_HEARTBEAT_S", "-3")
        assert importlib.reload(mod)._HEARTBEAT_S == 15.0

        monkeypatch.setenv("QUODEQ_SSE_HEARTBEAT_S", "2.5")
        assert importlib.reload(mod)._HEARTBEAT_S == 2.5
    finally:
        # Restore the module to its env-clean state for other tests.
        monkeypatch.delenv("QUODEQ_SSE_HEARTBEAT_S", raising=False)
        importlib.reload(mod)
