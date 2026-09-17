"""Cluster 37: UnixPty best-effort handlers log at debug."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

# The module imports fcntl/termios at import time, so a skip mark alone is
# not enough on Windows: skip at import.
_pty_unix = pytest.importorskip("quodeq.terminal._pty_unix", reason="POSIX only")


def _bare_pty() -> "_pty_unix.UnixPty":
    pty = object.__new__(_pty_unix.UnixPty)
    pty._master_fd = 12345
    pty._proc = None
    pty._selector = None
    return pty


def test_write_logs_when_master_is_closed(monkeypatch) -> None:
    def _bad_fd(*_args):
        raise OSError(9, "Bad file descriptor")

    monkeypatch.setattr(_pty_unix.os, "write", _bad_fd)
    with patch.object(_pty_unix._logger, "debug") as debug:
        _bare_pty().write(b"x")
    assert debug.called
    assert "pty write dropped" in debug.call_args.args[0]


def test_kill_logs_wait_timeout_and_close_failure(monkeypatch) -> None:
    class _Proc:
        pid = 424242

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("sh", timeout)

    def _bad_fd(*_args):
        raise OSError(9, "Bad file descriptor")

    pty = _bare_pty()
    pty._proc = _Proc()
    monkeypatch.setattr(_pty_unix, "kill_proc_tree", lambda proc: None)
    monkeypatch.setattr(_pty_unix.os, "close", _bad_fd)
    with patch.object(_pty_unix._logger, "debug") as debug:
        pty.kill()
    messages = [c.args[0] for c in debug.call_args_list]
    assert any("did not exit within" in m for m in messages)
    assert any("master close failed" in m for m in messages)
    assert pty._master_fd is None


def test_make_controlling_tty_survives_ioctl_failure(monkeypatch) -> None:
    if _pty_unix._TIOCSCTTY is None:
        pytest.skip("platform has no TIOCSCTTY")

    def _fails(*_args):
        raise OSError(25, "Inappropriate ioctl for device")

    monkeypatch.setattr(_pty_unix.fcntl, "ioctl", _fails)
    assert _pty_unix._make_controlling_tty() is None
