"""Smoke test that deadline_at is included in the SSE status payload."""
from quodeq.api._run_event_stream import serialize_status_event


def test_status_event_includes_deadline_at() -> None:
    payload = serialize_status_event({
        "state": "running",
        "phase": "analyzing",
        "deadline_at": "2026-05-02T11:00:00+00:00",
    })
    assert "deadline_at" in payload
    assert "2026-05-02T11:00:00+00:00" in payload
