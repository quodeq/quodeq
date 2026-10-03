"""Unit tests for the terminal WS session-setup helper.

Exercises ``setup_terminal_session`` directly against small fakes (no live
socket / werkzeug server), so the client-visible-on-failure behavior is
pinned without needing the full simple_websocket WS integration stack used
by tests/api/test_terminal_routes.py.
"""
from __future__ import annotations

import logging
import threading
from unittest.mock import patch

import pytest
from flask_sock import ConnectionClosed

from quodeq.api import _terminal_ws_helpers as ws_helpers
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
    """Simulates a spawn failure: ensure_session raises before a PTY exists.

    OSError, not RuntimeError: this is what a real PtyBackend.spawn() raises
    (os.openpty()/subprocess.Popen() failures are both OSError), and that is
    the exception type setup_terminal_session's except now narrows to.
    """

    def ensure_session(self, *, cwd, cols, rows):
        raise OSError("boom: shell spawn failed")

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


def test_setup_failure_logs_when_client_closed_before_fallback_frame():
    class _ClosedWs(_FakeWs):
        def send(self, data):
            raise ConnectionClosed()

    with patch.object(ws_helpers._logger, "warning"), patch.object(ws_helpers._logger, "debug") as debug:
        ok = setup_terminal_session(_RaisingManager(), _ClosedWs())
    assert ok is False
    assert debug.called
    assert "client already gone" in debug.call_args.args[0]


class _OneShotManager:
    """One chunk of data available, then idle forever (nothing left to send)."""

    def __init__(self):
        self.alive = True
        self._served = False

    def read(self, max_bytes=65536):
        if self._served:
            return ""
        self._served = True
        return "hi"


class TestPumpTerminalOut:
    """pump_terminal_out runs on its own daemon thread (terminal_routes.py's
    `_terminal_ws`), so it is the only thing that can signal `stop` for it.
    Its except was narrowed from bare `Exception` to (ConnectionClosed,
    OSError); the try/finally around the whole loop makes sure `stop` is
    still set even if something outside that tuple ends the loop instead."""

    def test_narrowed_exception_from_send_breaks_the_loop_and_signals_stop(self):
        class _OsErrorWs:
            def send(self, data):
                raise OSError("broken pipe")

        stop = threading.Event()
        ws_helpers.pump_terminal_out(_OneShotManager(), _OsErrorWs(), stop)
        assert stop.is_set()

    def test_an_exception_outside_the_tuple_still_signals_stop_before_propagating(self):
        class _WeirdWs:
            def send(self, data):
                raise RuntimeError("not a ConnectionClosed/OSError")

        stop = threading.Event()
        with pytest.raises(RuntimeError):
            ws_helpers.pump_terminal_out(_OneShotManager(), _WeirdWs(), stop)
        assert stop.is_set()


class _ReceiveRaisesWs:
    def __init__(self, exc):
        self._exc = exc

    def receive(self, timeout=None):
        raise self._exc


def _unused_apply_control(manager, payload):
    raise AssertionError("no control frame is sent")


class TestTerminalReadLoop:
    """A client disconnect is the normal end of a session: it stops the loop
    without a warning. Any other failure still warns with the traceback."""

    def test_client_disconnect_stops_the_loop_without_a_warning(self, caplog):
        stop = threading.Event()
        with caplog.at_level(logging.DEBUG, logger=ws_helpers.__name__):
            ws_helpers.terminal_read_loop(
                _ReceiveRaisesWs(ConnectionClosed()), _OkManager(), stop, _unused_apply_control
            )
        assert stop.is_set()
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_os_error_still_warns_with_the_traceback(self, caplog):
        stop = threading.Event()
        with caplog.at_level(logging.DEBUG, logger=ws_helpers.__name__):
            ws_helpers.terminal_read_loop(
                _ReceiveRaisesWs(OSError("pty gone")), _OkManager(), stop, _unused_apply_control
            )
        assert stop.is_set()
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == 1 and warnings[0].exc_info is not None
