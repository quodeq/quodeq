"""Menu bar process control — pidfile singleton, spawn/stop."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from quodeq.menubar import control


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(tmp_path))
    return tmp_path


def test_not_running_without_pidfile(run_dir):
    assert control.is_running() is False


_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="kill(pid, 0) liveness is POSIX-only; on Windows _pid_alive is a "
           "hard False (signal 0 is CTRL_C_EVENT and would interrupt the console)",
)


@_POSIX_ONLY
def test_running_with_live_pid(run_dir):
    control.write_pidfile()  # our own pid: definitely alive
    assert control.is_running() is True
    control.remove_pidfile()
    assert control.is_running() is False


def test_pid_alive_never_calls_kill_on_windows(run_dir):
    """Regression: os.kill(pid, 0) on Windows sends CTRL_C_EVENT to the whole
    console (it aborted entire CI runs), so the win32 branch must return
    before any os.kill call."""
    with patch.object(control.sys, "platform", "win32"), \
         patch.object(os, "kill") as kill:
        assert control._pid_alive(os.getpid()) is False
    kill.assert_not_called()


def test_stale_pidfile_cleaned(run_dir):
    (run_dir / "menubar.pid").write_text("999999999")
    assert control.is_running() is False
    assert not (run_dir / "menubar.pid").exists()


def test_garbage_pidfile_cleaned(run_dir):
    (run_dir / "menubar.pid").write_text("not-a-pid")
    assert control.is_running() is False
    assert not (run_dir / "menubar.pid").exists()


def test_spawn_launches_detached_menubar(run_dir):
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(subprocess, "Popen") as popen:
        assert control.spawn() is True
    cmd = popen.call_args.args[0]
    assert cmd == [sys.executable, "-m", "quodeq.menubar"]
    assert popen.call_args.kwargs["start_new_session"] is True
    assert popen.call_args.kwargs["stdout"] == subprocess.DEVNULL
    assert popen.call_args.kwargs["stderr"] == subprocess.DEVNULL


def test_spawn_noop_when_running(run_dir):
    control.write_pidfile()
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(subprocess, "Popen") as popen:
        assert control.spawn() is False
    popen.assert_not_called()


def test_spawn_noop_when_unsupported(run_dir):
    with patch.object(control, "is_supported", return_value=False), \
         patch.object(subprocess, "Popen") as popen:
        assert control.spawn() is False
    popen.assert_not_called()


def test_spawn_survives_popen_failure(run_dir):
    with patch.object(control, "is_supported", return_value=True), \
         patch.object(subprocess, "Popen", side_effect=OSError("nope")):
        assert control.spawn() is False


@_POSIX_ONLY
def test_stop_sigterms_pidfile_process(run_dir):
    (run_dir / "menubar.pid").write_text("12345")
    with patch.object(os, "kill") as kill:
        # First call is the liveness probe (sig 0); make it succeed.
        kill.return_value = None
        assert control.stop() is True
    kill.assert_any_call(12345, signal.SIGTERM)
    assert not (run_dir / "menubar.pid").exists()


def test_stop_without_pidfile(run_dir):
    assert control.stop() is False


def test_is_supported_false_off_macos():
    with patch.object(control.sys, "platform", "linux"):
        assert control.is_supported() is False


def test_is_supported_on_macos_with_rumps():
    with patch.object(control.sys, "platform", "darwin"), \
         patch.object(control.importlib.util, "find_spec", return_value=MagicMock()):
        assert control.is_supported() is True
