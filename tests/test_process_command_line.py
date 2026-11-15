"""process_has_arg checks the command line on every platform: a live PID alone is never proof."""
from __future__ import annotations

import subprocess
import types

import pytest

from quodeq.shared import process


@pytest.fixture
def windows(monkeypatch, windows_system_tools):
    monkeypatch.setattr(process, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(process, "_on_windows", lambda: True)
    calls: list[list[str]] = []

    def answer(stdout: str | None):
        def run(cmd, **_kw):
            calls.append(cmd)
            if stdout is None:
                raise OSError("no powershell")
            return types.SimpleNamespace(stdout=stdout)
        monkeypatch.setattr(process.subprocess, "run", run)
    return answer, calls


def test_windows_matches_a_quodeq_command_line(windows):
    answer, calls = windows
    answer('"C:\\Program Files\\Python\\python.exe" -m quodeq.api.app\r\n')
    assert process.process_has_arg(4242, "quodeq.api.app")
    assert "ProcessId=4242" in " ".join(calls[0])


def test_windows_refuses_a_reused_pid(windows):
    answer, _ = windows
    answer("C:\\Windows\\notepad.exe\r\n")
    assert not process.process_has_arg(4242, "quodeq.api.app")


def test_windows_refuses_when_the_command_line_cannot_be_read(windows):
    answer, _ = windows
    answer(None)
    assert not process.process_has_arg(4242, "quodeq.api.app")


def test_a_timeout_is_refused(monkeypatch):
    monkeypatch.setattr(process, "is_pid_alive", lambda pid: True)

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 5))
    monkeypatch.setattr(process.subprocess, "run", slow)
    assert not process.process_has_arg(4242, "quodeq.api.app")
