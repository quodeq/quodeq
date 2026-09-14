"""_on_open: bringing the dashboard window to front (or re-launching it) must
not crash the menu bar app when subprocess.Popen fails (cluster 10,
fault-tolerance cycle 1). Mirrors _launch_dashboard_process's `except
OSError` handling in the same class.
"""
from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from quodeq.menubar import _app_lifecycle

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="menubar app only ever runs on macOS",
)


class _FakeApp(_app_lifecycle.DashboardLifecycleMixin):
    """Minimal stand-in for the QuodeqApp host the mixin expects."""

    def __init__(self, port: int | None, *, find_port_result: int | None = None) -> None:
        self._state_lock = threading.Lock()
        self._port = port
        self._find_port_result = find_port_result
        self.errors: list[str] = []

    def _find_running_port(self) -> int | None:
        return self._find_port_result

    def _set_error(self, msg: str) -> None:
        self.errors.append(msg)


class TestOnOpenPopenFailure:
    def test_oserror_from_popen_is_caught_and_reported(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise OSError("no such file or directory: quodeq")

        monkeypatch.setattr(_app_lifecycle.subprocess, "Popen", _raise)
        app = _FakeApp(port=7863)

        app._on_open(None)  # must not raise

        assert app.errors == ["Failed: no such file or directory: quodeq"]

    def test_successful_popen_reports_no_error(self, monkeypatch):
        calls = []

        def _fake_popen(cmd, **kwargs):
            calls.append(cmd)
            return object()

        monkeypatch.setattr(_app_lifecycle.subprocess, "Popen", _fake_popen)
        app = _FakeApp(port=7863)

        app._on_open(None)

        assert app.errors == []
        assert len(calls) == 1

    def test_no_running_port_skips_popen_entirely(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            _app_lifecycle.subprocess, "Popen",
            lambda *a, **kw: calls.append(1),
        )
        app = _FakeApp(port=None, find_port_result=None)

        app._on_open(None)

        assert calls == []
        assert app.errors == []
