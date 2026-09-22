"""kill_port_processes must only kill quodeq's own dashboard process."""
from __future__ import annotations

from quodeq.menubar import _process


def test_kill_port_processes_skips_non_quodeq_pid(monkeypatch):
    killed = []
    monkeypatch.setattr(_process, "find_pids_on_port", lambda port: [111, 222])
    monkeypatch.setattr(_process, "_is_quodeq_process", lambda pid: pid == 222)
    monkeypatch.setattr(_process.os, "kill", lambda pid, sig: killed.append(pid))

    _process.kill_port_processes(9999)

    assert killed == [222]


def test_kill_port_processes_kills_own_process(monkeypatch):
    killed = []
    monkeypatch.setattr(_process, "find_pids_on_port", lambda port: [333])
    monkeypatch.setattr(_process, "_is_quodeq_process", lambda pid: pid == 333)
    monkeypatch.setattr(_process.os, "kill", lambda pid, sig: killed.append(pid))

    _process.kill_port_processes(9999)

    assert killed == [333]


def test_kill_port_processes_kills_nothing_when_all_unrelated(monkeypatch):
    killed = []
    monkeypatch.setattr(_process, "find_pids_on_port", lambda port: [111, 444])
    monkeypatch.setattr(_process, "_is_quodeq_process", lambda pid: False)
    monkeypatch.setattr(_process.os, "kill", lambda pid, sig: killed.append(pid))

    _process.kill_port_processes(9999)

    assert killed == []


class _FakeCompletedProcess:
    def __init__(self, stdout: str):
        self.stdout = stdout


def test_is_quodeq_process_true_for_quodeq_command(monkeypatch):
    monkeypatch.setattr(
        _process.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess("/opt/homebrew/bin/quodeq dashboard\n"),
    )

    assert _process._is_quodeq_process(123) is True


def test_is_quodeq_process_false_for_unrelated_command(monkeypatch):
    monkeypatch.setattr(
        _process.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess("/usr/bin/python3 -m http.server\n"),
    )

    assert _process._is_quodeq_process(456) is False


def test_is_quodeq_process_false_on_subprocess_error(monkeypatch):
    def _raise(*a, **kw):
        raise OSError("ps not found")

    monkeypatch.setattr(_process.subprocess, "run", _raise)

    assert _process._is_quodeq_process(789) is False
