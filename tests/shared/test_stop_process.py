"""stop_process: end one process, also from a Windows app that has no console."""
from __future__ import annotations

import signal

import pytest

from quodeq.shared import process_kill

_CTRL_BREAK = 1  # signal.CTRL_BREAK_EVENT, which only exists on Windows


@pytest.fixture
def windows(monkeypatch):
    """Pretend to be Windows and record every signal sent."""
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(process_kill.sys, "platform", "win32")
    monkeypatch.setattr(process_kill, "_CTRL_BREAK", _CTRL_BREAK)
    monkeypatch.setattr(process_kill.time, "sleep", lambda _s: None)
    monkeypatch.setattr(process_kill.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    return sent


def test_posix_sends_sigterm(monkeypatch):
    sent = []
    monkeypatch.setattr(process_kill.sys, "platform", "linux")
    monkeypatch.setattr(process_kill.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    process_kill.stop_process(1234)
    assert sent == [(1234, signal.SIGTERM)]


def test_windows_asks_politely_when_the_process_then_exits(windows, monkeypatch):
    monkeypatch.setattr(process_kill, "is_pid_alive", lambda _pid: False)
    process_kill.stop_process(1234)
    assert windows == [(1234, _CTRL_BREAK)]


def test_windows_without_a_console_falls_back_to_terminating(monkeypatch, windows):
    # A windowed exe has no console, so the console event cannot be sent.
    def kill(pid, sig):
        if sig == _CTRL_BREAK:
            raise OSError(6, "The handle is invalid")
        windows.append((pid, sig))

    monkeypatch.setattr(process_kill.os, "kill", kill)
    monkeypatch.setattr(process_kill, "is_pid_alive", lambda _pid: True)
    process_kill.stop_process(1234)
    assert windows == [(1234, signal.SIGTERM)]


def test_windows_terminates_a_process_that_ignored_the_request(windows, monkeypatch):
    # The event was accepted but never reached the process (different console).
    monkeypatch.setattr(process_kill, "is_pid_alive", lambda _pid: True)
    process_kill.stop_process(1234)
    assert windows == [(1234, _CTRL_BREAK), (1234, signal.SIGTERM)]


def test_windows_process_already_gone_is_not_an_error(monkeypatch, windows):
    def kill(_pid, _sig):
        raise OSError(87, "The parameter is incorrect")

    monkeypatch.setattr(process_kill.os, "kill", kill)
    monkeypatch.setattr(process_kill, "is_pid_alive", lambda _pid: False)
    process_kill.stop_process(1234)
    assert windows == []
