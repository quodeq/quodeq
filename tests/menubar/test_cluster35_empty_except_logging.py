"""Cluster 35: menubar best-effort handlers log at debug instead of swallowing."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from quodeq.menubar import _app_lifecycle, _process, control, state


def test_remove_pidfile_logs_when_unlink_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(control, "_pidfile_path", lambda: tmp_path)  # a directory: unlink raises an OSError subclass
    with patch.object(control._logger, "debug") as debug:
        control.remove_pidfile()
    assert debug.called
    assert "pidfile" in debug.call_args.args[0]


def test_cleanup_stderr_log_logs_missing_file(tmp_path) -> None:
    with patch.object(_process._logger, "debug") as debug:
        _process.cleanup_stderr_log(str(tmp_path / "gone.log"))
    assert debug.called
    assert "not removed" in debug.call_args.args[0]


def test_kill_port_processes_logs_unsignalable_pid(monkeypatch) -> None:
    monkeypatch.setattr(_process, "find_pids_on_port", lambda port: [424242])
    monkeypatch.setattr(_process, "_is_quodeq_process", lambda pid: True)

    def _gone(*_args):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(_process.os, "kill", _gone)
    with patch.object(_process._logger, "debug") as debug:
        _process.kill_port_processes(7863)
    assert debug.called
    assert "could not signal pid" in debug.call_args.args[0]


def test_write_state_logs_write_and_cleanup_failures(monkeypatch, tmp_path) -> None:
    env = {"QUODEQ_DIR": str(tmp_path)}
    current = state.read_state(env)

    def _replace_fails(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    def _unlink_fails(*_args, **_kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(state.os, "replace", _replace_fails)
    monkeypatch.setattr(state.os, "unlink", _unlink_fails)
    with patch.object(state._logger, "debug") as debug:
        state.write_state(current, env)  # must not raise
    messages = [c.args[0] for c in debug.call_args_list]
    assert any("state write failed" in m for m in messages)
    assert any("not removed" in m for m in messages)


class _FakeSweepApp(_app_lifecycle.DashboardLifecycleMixin):
    """Minimal stand-in for the QuodeqApp host: _sweep_stragglers only
    touches self._ports."""

    def __init__(self) -> None:
        self._ports = [7863]


def test_sweep_stragglers_logs_pkill_failure(monkeypatch) -> None:
    monkeypatch.setattr(_app_lifecycle, "_kill_port_processes", lambda port: None)

    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("pkill", 1)

    monkeypatch.setattr(_app_lifecycle.subprocess, "run", _raise)
    app = _FakeSweepApp()
    with patch.object(_app_lifecycle._logger, "debug") as debug:
        app._sweep_stragglers()
    assert debug.called
    assert "pkill" in debug.call_args.args[0]


def test_wait_for_dashboard_logs_stderr_close_failure(monkeypatch) -> None:
    """The finally block's stderr_log.close() failure must not be silent.

    A process that "crashed" (poll() returns non-None) makes wait_for_dashboard
    return after its first iteration, via the on_crash callback, so the finally
    block runs deterministically without waiting out the full retry loop.
    """
    monkeypatch.setattr(_process.time, "sleep", lambda _seconds: None)

    class _CrashedProcess:
        def poll(self):
            return 1

    class _FailingStderrLog:
        def close(self):
            raise OSError("close failed")

    callbacks = _process.DashboardCallbacks(
        on_port_found=lambda port, log: None,
        on_crash=lambda log: None,
        on_timeout=lambda: None,
    )
    with patch.object(_process._logger, "debug") as debug:
        _process.wait_for_dashboard(
            _CrashedProcess(),
            (7863,),
            _process.DashboardState(cache={}, last_known=None),
            _FailingStderrLog(),
            callbacks,
        )
    assert debug.called
    assert "stderr log close failed" in debug.call_args.args[0]
