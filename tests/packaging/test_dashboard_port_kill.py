"""kill_port_processes must only kill quodeq's own dashboard process.

Note: this module is imported as the bare sibling name ``_dashboard`` (with
``packaging/macos`` added to ``sys.path``), not as ``packaging.macos._dashboard``.
An installed PyPI package named ``packaging`` shadows the local ``packaging/``
directory, so the dotted import path does not resolve. See
tests/packaging/test_menubar_update.py for the same convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

_MACOS_DIR = str(Path(__file__).resolve().parents[2] / "packaging" / "macos")
if _MACOS_DIR not in sys.path:
    sys.path.insert(0, _MACOS_DIR)

import _dashboard  # noqa: E402


def test_kill_port_processes_skips_non_quodeq_pid(monkeypatch):
    killed = []
    monkeypatch.setattr(_dashboard, "find_pids_on_port", lambda port: [111, 222])
    monkeypatch.setattr(_dashboard, "_is_quodeq_process", lambda pid: pid == 222)
    monkeypatch.setattr(_dashboard.os, "kill", lambda pid, sig: killed.append(pid))

    _dashboard.kill_port_processes(9999)

    assert killed == [222]


def test_kill_port_processes_kills_own_process(monkeypatch):
    killed = []
    monkeypatch.setattr(_dashboard, "find_pids_on_port", lambda port: [333])
    monkeypatch.setattr(_dashboard, "_is_quodeq_process", lambda pid: pid == 333)
    monkeypatch.setattr(_dashboard.os, "kill", lambda pid, sig: killed.append(pid))

    _dashboard.kill_port_processes(9999)

    assert killed == [333]


def test_kill_port_processes_kills_nothing_when_all_unrelated(monkeypatch):
    killed = []
    monkeypatch.setattr(_dashboard, "find_pids_on_port", lambda port: [111, 444])
    monkeypatch.setattr(_dashboard, "_is_quodeq_process", lambda pid: False)
    monkeypatch.setattr(_dashboard.os, "kill", lambda pid, sig: killed.append(pid))

    _dashboard.kill_port_processes(9999)

    assert killed == []


class _FakeCompletedProcess:
    def __init__(self, stdout: str):
        self.stdout = stdout


def test_is_quodeq_process_true_for_quodeq_command(monkeypatch):
    monkeypatch.setattr(
        _dashboard.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess("/opt/homebrew/bin/quodeq dashboard\n"),
    )

    assert _dashboard._is_quodeq_process(123) is True


def test_is_quodeq_process_false_for_unrelated_command(monkeypatch):
    monkeypatch.setattr(
        _dashboard.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess("/usr/bin/python3 -m http.server\n"),
    )

    assert _dashboard._is_quodeq_process(456) is False


def test_is_quodeq_process_false_on_subprocess_error(monkeypatch):
    def _raise(*a, **kw):
        raise OSError("ps not found")

    monkeypatch.setattr(_dashboard.subprocess, "run", _raise)

    assert _dashboard._is_quodeq_process(789) is False
