"""On Linux without a GTK/WebKit2GTK backend, the dashboard must fall back to
the browser instead of crashing (exercises dashboard/_server.py:142).

Deterministic on any host: sys.platform and the backend probe are patched, so
it asserts the fallback contract without needing a real Linux/GTK environment.
"""
from __future__ import annotations

from quodeq.dashboard import _server
from quodeq.dashboard._probes import NativeShell
from quodeq.dashboard.cli import parse_args
import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_serve_native_falls_back_to_browser_when_gtk_missing(monkeypatch) -> None:
    opened: list[str] = []
    served: list[bool] = []
    monkeypatch.setattr(_server.sys, "platform", "linux")
    shell = NativeShell(
        webview_importable=lambda: True,
        linux_backend_available=lambda: False,
        open_browser=opened.append,
    )

    _server._serve_native(
        "http://127.0.0.1:7863", None, lambda: None,
        shell=shell, serve_blocking=lambda proc, stop: served.append(True),
    )

    assert opened == ["http://127.0.0.1:7863"], "should open the dashboard URL in a browser"
    assert served == [True], "should keep serving the API after falling back"


def test_serve_native_falls_back_to_browser_when_dotnet_cannot_load(monkeypatch) -> None:
    # Windows on ARM: pythonnet's .NET shim is x86/x64 only, so the window would die on import.
    opened: list[str] = []
    served: list[bool] = []
    spawned: list[bool] = []
    monkeypatch.setattr(_server.sys, "platform", "win32")
    shell = NativeShell(
        webview_importable=lambda: True,
        windows_backend_available=lambda: False,
        spawn_window=lambda *_a, **_k: spawned.append(True),
        open_browser=opened.append,
    )

    _server._serve_native(
        "http://127.0.0.1:7863", None, lambda: None,
        shell=shell, serve_blocking=lambda proc, stop: served.append(True),
    )

    assert opened == ["http://127.0.0.1:7863"], "should open the dashboard URL in a browser"
    assert served == [True], "should keep serving the API after falling back"
    assert spawned == [], "should not spawn a window that cannot start"


# --- Detached launch: the launcher hands the terminal back once the window is up ---
# (lives here because this file already imports _server; see _detach.py)


@pytest.mark.parametrize(("flags", "detaches"), [
    ([], True),
    (["--dev"], False),
    (["--verbose"], False),
    (["--foreground"], False),
    (["--browser"], False),
    (["--no-open"], False),
])
def test_only_a_plain_window_launch_detaches(monkeypatch, flags, detaches) -> None:
    monkeypatch.setattr(sys.modules["quodeq.dashboard._detach"], "IS_WIN32", False)
    assert _server.choose_detach(parse_args(flags)) is detaches


def test_windows_never_detaches(monkeypatch) -> None:
    monkeypatch.setattr(sys.modules["quodeq.dashboard._detach"], "IS_WIN32", True)
    assert _server.choose_detach(parse_args([])) is False


def _native(tmp_path: Path, *, window_alive: bool, bind_socket: bool) -> tuple[list, list]:
    sock = tmp_path / "quodeq.sock"
    window = MagicMock()
    window.poll.return_value = None if window_alive else 1
    instance = MagicMock(sock_path=sock)
    instance.probe_existing.return_value = False

    def spawn(*_a, **_k):
        if bind_socket:
            sock.touch()
        return window

    served, stopped = [], []
    shell = NativeShell(webview_importable=lambda: True, linux_backend_available=lambda: True,
                        windows_backend_available=lambda: True,
                        make_instance=lambda: instance, spawn_window=spawn)
    _server._serve_native("http://127.0.0.1:7863", MagicMock(pid=42), lambda: stopped.append(True),
                          shell=shell, serve_blocking=lambda proc, stop: served.append(True), detach=True)
    return served, stopped


def test_detached_launch_returns_once_the_window_owns_its_socket(tmp_path) -> None:
    served, stopped = _native(tmp_path, window_alive=True, bind_socket=True)
    assert served == [] and stopped == [], "the window, not the launcher, now stops the API"


def test_detached_launch_stays_in_the_foreground_when_the_window_dies(tmp_path) -> None:
    served, stopped = _native(tmp_path, window_alive=False, bind_socket=False)
    assert served == [True], "a window that never came up leaves the terminal in charge"


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP is POSIX-only")
def test_a_closing_terminal_stops_the_api() -> None:
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGTSTP)}
    stopped: list[bool] = []
    try:
        _server._register_serve_signal_handlers(lambda: stopped.append(True))
        with pytest.raises(SystemExit):
            signal.getsignal(signal.SIGHUP)(signal.SIGHUP, None)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    assert stopped == [True]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP is POSIX-only")
def test_nohup_keeps_the_api_running_when_the_terminal_closes() -> None:
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGTSTP)}
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)  # what `nohup` sets before exec
        _server._register_serve_signal_handlers(lambda: None)
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
