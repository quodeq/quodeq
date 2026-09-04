"""Unit tests for the terminal WS session-setup helper.

Exercises ``setup_terminal_session`` directly against small fakes (no live
socket / werkzeug server), so the client-visible-on-failure behavior is
pinned without needing the full simple_websocket WS integration stack used
by tests/api/test_terminal_routes.py.
"""
from __future__ import annotations

from quodeq.api._terminal_ws_helpers import setup_terminal_session


class _FakeWs:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, data):
        self.sent.append(data)


class _OkManager:
    def __init__(self, scrollback=""):
        self._scrollback = scrollback

    def ensure_session(self, *, cwd, cols, rows):
        pass

    def scrollback(self):
        return self._scrollback


class _RaisingManager:
    """Simulates a spawn failure: ensure_session raises before a PTY exists."""

    def ensure_session(self, *, cwd, cols, rows):
        raise RuntimeError("boom: shell spawn failed")

    def scrollback(self):  # pragma: no cover - must not be reached
        raise AssertionError("scrollback() must not run after a failed ensure_session")


def test_setup_success_replays_scrollback_and_returns_true():
    ws = _FakeWs()
    ok = setup_terminal_session(_OkManager(scrollback="hi\n"), ws)
    assert ok is True
    assert ws.sent == ["0hi\n"]


def test_setup_success_with_no_scrollback_sends_nothing():
    ws = _FakeWs()
    ok = setup_terminal_session(_OkManager(scrollback=""), ws)
    assert ok is True
    assert ws.sent == []


def test_setup_failure_sends_error_over_socket():
    ws = _FakeWs()
    ok = setup_terminal_session(_RaisingManager(), ws)
    assert ok is False
    # Sent with the "0" (data) prefix, matching this handler's other
    # client-visible message (terminal_routes.py's "already open in another
    # window" banner): the frontend's WS handler only renders "0"-prefixed
    # frames (useTerminalSocket.js's onmessage), so a "1"-prefixed message
    # would be silently dropped and never reach the terminal pane.
    assert len(ws.sent) == 1
    assert ws.sent[0][0] == "0"
    assert "could not be started" in ws.sent[0]


def test_setup_failure_swallows_send_error_on_disconnected_client():
    class _DeadWs(_FakeWs):
        def send(self, data):
            raise ConnectionError("client already gone")

    ok = setup_terminal_session(_RaisingManager(), _DeadWs())
    assert ok is False  # must not raise past this point
