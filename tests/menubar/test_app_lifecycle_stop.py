"""_on_stop: process-group kill, straggler sweep, UI reset, stderr cleanup.

No real signals or processes: ``os.killpg``/``os.getpgid``,
``subprocess.run`` and ``_kill_port_processes`` are monkeypatched on
``_app_lifecycle`` itself, and the dashboard process is a fake object.
"""
from __future__ import annotations

import signal
import subprocess
import threading
from pathlib import Path

import pytest

from quodeq.menubar import _app_lifecycle
from quodeq.menubar._app_lifecycle import _PKILL_TIMEOUT_S, _PROCESS_PATTERNS


class _FakeProcess:
    def __init__(self, *, pid: int = 4321, poll_result: int | None = None) -> None:
        self.pid = pid
        self._poll_result = poll_result
        self.terminated = False

    def poll(self) -> int | None:
        return self._poll_result

    def terminate(self) -> None:
        self.terminated = True


class _FakeMenuItem:
    def __init__(self) -> None:
        self.title = ""


class _FakeApp(_app_lifecycle.DashboardLifecycleMixin):
    """Minimal stand-in for the QuodeqApp host the mixin expects."""

    def __init__(self, process, stderr_log_path: str | None = None) -> None:
        self._process = process
        self._ports = [7863, 7864, 7865]
        self._state_lock = threading.Lock()
        self._port = 7863
        self._status_item = _FakeMenuItem()
        self._stderr_log_path = stderr_log_path
        self.ui_states: list[bool] = []

    def _set_ui_state(self, running: bool) -> None:
        self.ui_states.append(running)


class _Recorder:
    def __init__(self) -> None:
        self.killpg: list[tuple[int, int]] = []
        self.ports: list[int] = []
        self.runs: list[tuple[list[str], bool, int]] = []


@pytest.fixture
def rec(monkeypatch) -> _Recorder:
    """Intercept every process-touching call _on_stop makes."""
    recorder = _Recorder()
    monkeypatch.setattr(_app_lifecycle.os, "getpgid", lambda pid: pid + 1000)
    monkeypatch.setattr(
        _app_lifecycle.os, "killpg",
        lambda pgid, sig: recorder.killpg.append((pgid, sig)),
    )
    monkeypatch.setattr(
        _app_lifecycle, "_kill_port_processes", recorder.ports.append,
    )
    monkeypatch.setattr(
        _app_lifecycle.subprocess, "run",
        lambda args, **kw: recorder.runs.append(
            (args, kw.get("capture_output"), kw.get("timeout")),
        ),
    )
    return recorder


class TestProcessGroupTermination:
    def test_running_process_gets_killpg_sigterm(self, rec):
        process = _FakeProcess(pid=4321)
        app = _FakeApp(process)

        app._on_stop(None)

        assert rec.killpg == [(5321, signal.SIGTERM)]
        assert process.terminated is False
        assert app._process is None

    def test_process_lookup_error_falls_back_to_terminate(self, rec, monkeypatch):
        def _raise(pgid, sig):
            raise ProcessLookupError("no such process group")

        monkeypatch.setattr(_app_lifecycle.os, "killpg", _raise)
        process = _FakeProcess()
        app = _FakeApp(process)

        app._on_stop(None)

        assert process.terminated is True
        assert app._process is None

    def test_oserror_falls_back_to_terminate(self, rec, monkeypatch):
        def _raise(pgid, sig):
            raise OSError("killpg unavailable")

        monkeypatch.setattr(_app_lifecycle.os, "killpg", _raise)
        process = _FakeProcess()
        app = _FakeApp(process)

        app._on_stop(None)

        assert process.terminated is True
        assert app._process is None

    def test_exited_process_is_not_signalled_and_handle_is_kept(self, rec):
        # poll() returning an exit code means the process is already gone:
        # no signal, and the handle stays put (it is only cleared inside the
        # branch that actually killed something).
        process = _FakeProcess(poll_result=0)
        app = _FakeApp(process)

        app._on_stop(None)

        assert rec.killpg == []
        assert process.terminated is False
        assert app._process is process

    def test_missing_process_skips_the_kill(self, rec):
        app = _FakeApp(None)

        app._on_stop(None)

        assert rec.killpg == []
        assert app._process is None


class TestStragglerSweep:
    def test_kill_port_processes_called_once_per_port(self, rec):
        app = _FakeApp(_FakeProcess())

        app._on_stop(None)

        assert rec.ports == [7863, 7864, 7865]

    def test_pkill_runs_once_per_pattern_with_timeout(self, rec):
        app = _FakeApp(_FakeProcess())

        app._on_stop(None)

        assert rec.runs == [
            (["pkill", "-f", pattern], True, _PKILL_TIMEOUT_S)
            for pattern in _PROCESS_PATTERNS
        ]

    def test_pkill_failures_do_not_abort_the_stop(self, rec, monkeypatch):
        errors = iter([
            subprocess.TimeoutExpired(cmd="pkill", timeout=_PKILL_TIMEOUT_S),
            OSError("pkill missing"),
        ])

        def _raise(args, **kw):
            raise next(errors, OSError("pkill missing"))

        monkeypatch.setattr(_app_lifecycle.subprocess, "run", _raise)
        app = _FakeApp(_FakeProcess())

        app._on_stop(None)

        assert app.ui_states == [False]
        assert app._status_item.title == "Stopped"


class TestStopResetsState:
    def test_ui_state_is_reset(self, rec):
        app = _FakeApp(_FakeProcess())

        app._on_stop(None)

        assert app._port is None
        assert app._status_item.title == "Stopped"
        assert app.ui_states == [False]

    def test_stderr_log_is_removed(self, rec, tmp_path: Path):
        stderr_log = tmp_path / "quodeq-dashboard.log"
        stderr_log.write_text("boom", encoding="utf-8")
        app = _FakeApp(_FakeProcess(), stderr_log_path=str(stderr_log))

        app._on_stop(None)

        assert not stderr_log.exists()
        assert app._stderr_log_path is None
