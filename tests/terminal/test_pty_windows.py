"""Unit coverage for the Windows ConPTY backend's dead-process guards.

pywinpty is Windows-only (pyproject pins it `; sys_platform == "win32"`), so
`winpty` is stubbed into sys.modules before import here -- same pattern
tests/menubar/test_app.py uses for rumps -- letting these guards be exercised
on any dev/CI platform. This complements test_pty_windows_smoke.py, which
exercises the real ConPTY backend but only runs on win32.

Part of Cluster 12 (terminal PTY reliability): see also
tests/integration/test_terminal_pty_reliability_e2e.py for the shared
end-to-end regression test that ties this fix together with the
terminal_read_loop / pump_terminal_out stop-signal fix.
"""
from __future__ import annotations

import logging
import sys
import types

import pytest


class _FakeWinProcess:
    """Minimal stand-in for winpty.PtyProcess."""

    pid = 4242

    def __init__(self):
        self._alive = True
        self.write_calls: list[str] = []

    @classmethod
    def spawn(cls, cmd, cwd=None, env=None, dimensions=None):
        return cls()

    def isalive(self):
        return self._alive

    def write(self, s):
        self.write_calls.append(s)

    def read(self, n):
        return ""

    def setwinsize(self, rows, cols):
        pass

    def terminate(self, force=False):
        # Simulates the process already being gone (e.g. reaped by the OS
        # between isalive() going False and terminate() being called).
        raise OSError("process already terminated")


@pytest.fixture
def windows_pty_module(monkeypatch):
    fake_winpty = types.ModuleType("winpty")
    fake_winpty.PtyProcess = _FakeWinProcess
    monkeypatch.setitem(sys.modules, "winpty", fake_winpty)
    # Force a fresh import so the module binds to this test's fake rather
    # than whatever an earlier test may have left cached.
    monkeypatch.delitem(sys.modules, "quodeq.terminal._pty_windows", raising=False)
    import quodeq.terminal._pty_windows as mod
    return mod


def test_write_to_dead_process_is_a_noop_not_an_exception(windows_pty_module):
    """Root-cause fix: write() now guards on isalive(), matching read()
    (which already had this guard two lines above the old, unguarded write())."""
    pty = windows_pty_module.WindowsPty(argv=["cmd.exe"])
    pty.spawn(cwd="C:\\", cols=80, rows=24)
    proc = pty._proc
    proc._alive = False  # process died mid-session

    pty.write(b"echo still-writing\r\n")  # must not raise

    assert proc.write_calls == []  # guard skipped the write entirely


def test_write_to_live_process_still_writes(windows_pty_module):
    """The guard must not turn write() into a no-op for a live process."""
    pty = windows_pty_module.WindowsPty(argv=["cmd.exe"])
    pty.spawn(cwd="C:\\", cols=80, rows=24)

    pty.write(b"echo hi\r\n")

    assert pty._proc.write_calls == ["echo hi\r\n"]


def test_kill_logs_a_swallowed_terminate_failure(windows_pty_module, caplog):
    """kill()'s except Exception: pass previously swallowed silently -- no
    logger existed anywhere in this file. It must now log."""
    pty = windows_pty_module.WindowsPty(argv=["cmd.exe"])
    pty.spawn(cwd="C:\\", cols=80, rows=24)

    with caplog.at_level(logging.WARNING, logger="quodeq.terminal._pty_windows"):
        pty.kill()  # _FakeWinProcess.terminate() raises; must not propagate

    assert any(
        r.levelno >= logging.WARNING and "terminate" in r.message.lower()
        for r in caplog.records
    )
