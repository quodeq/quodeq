"""More machine-readable error-code coverage for assistant_turn_routes.py:
tools/check_error_codes.py's zero-tolerance gate still found three sites
bare after the first pass -- missing text, stop-with-no-turn-running, and
the events stream's unknown-session 404.

Sibling of test_assistant_error_codes.py, which sits at 232 of its 240-line
budget: new coverage goes in a new file instead of growing it. The ``app``
fixture is reused, not copied, from test_assistant_routes.py.
"""
from __future__ import annotations

from tests.api._assistant_routes_fixtures import app  # noqa: F401 -- pytest fixture


def test_post_message_missing_text_has_code(app):
    client = app.test_client()
    sid = client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "   "})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_PARAM"


def test_stop_turn_unknown_session_has_code(app):
    client = app.test_client()
    resp = client.post("/api/assistant/sessions/nope/stop")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "UNKNOWN_SESSION"


def test_stop_turn_no_turn_running_has_code(app):
    client = app.test_client()
    sid = client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/stop")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "NO_TURN_RUNNING"


def test_events_stream_unknown_session_has_code(app):
    client = app.test_client()
    resp = client.get("/api/assistant/sessions/nope/events?after=0")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "UNKNOWN_SESSION"
