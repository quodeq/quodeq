"""dashboard best-effort handlers log at debug instead of swallowing."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard import _instance as instance
from quodeq.dashboard import _process
from quodeq.dashboard import _server as server
from quodeq.dashboard import _webview_token as webview_token
from quodeq.dashboard import _webview_window as webview_window
from quodeq.dashboard import _webview_window_about as about
from quodeq.dashboard import _webview_window_native_ops as native_ops
from quodeq.dashboard import _webview_window_fullscreen as fullscreen


def _fake_appkit_with_broken_bundle() -> types.ModuleType:
    """AppKit stub whose NSBundle.mainBundle().infoDictionary() raises AttributeError."""
    mod = types.ModuleType("AppKit")

    class _Bundle:
        @staticmethod
        def mainBundle():
            raise AttributeError("no bundle in tests")

    class _Image:
        @staticmethod
        def alloc():
            raise AttributeError("no NSImage in tests")

    class _App:
        @staticmethod
        def sharedApplication():
            raise AttributeError("no NSApp in tests")

    mod.NSBundle = _Bundle
    mod.NSImage = _Image
    mod.NSApplication = _App
    return mod


def _fake_appkit_with_broken_app() -> types.ModuleType:
    """AppKit stub where the bundle patch and icon load succeed but
    NSApplication access raises."""
    mod = types.ModuleType("AppKit")

    class _MainBundle:
        @staticmethod
        def infoDictionary():
            return {}

    class _Bundle:
        @staticmethod
        def mainBundle():
            return _MainBundle()

    class _LoadedImage:
        def initWithContentsOfFile_(self, _path):
            return self

    class _Image:
        @staticmethod
        def alloc():
            return _LoadedImage()

    class _App:
        @staticmethod
        def sharedApplication():
            raise AttributeError("no NSApp in tests")

    mod.NSBundle = _Bundle
    mod.NSImage = _Image
    mod.NSApplication = _App
    return mod


def test_set_macos_app_identity_logs_bundle_patch_failure(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "AppKit", _fake_appkit_with_broken_bundle())
    monkeypatch.setattr(about, "icon_path", lambda ext: None)  # stop after the bundle patch
    messages: list[str] = []
    monkeypatch.setattr(about, "log_debug", messages.append)
    about.set_macos_app_identity()
    assert any("bundle name patch skipped" in m for m in messages)


def test_set_macos_app_identity_logs_dock_icon_failure(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "AppKit", _fake_appkit_with_broken_app())
    monkeypatch.setattr(about, "icon_path", lambda ext: "/tmp/fake.icns")
    messages: list[str] = []
    monkeypatch.setattr(about, "log_debug", messages.append)
    about.set_macos_app_identity()
    assert any("dock icon not set" in m for m in messages)


class _Raising:
    """Stand-in for ctypes.windll that raises AttributeError on any access,
    so the test exercises the except branch on every platform, including
    real Windows where ctypes.windll exists and would otherwise succeed."""

    def __getattr__(self, name):
        raise AttributeError(name)


def test_set_app_icon_logs_windows_taskbar_failure(monkeypatch) -> None:
    monkeypatch.setattr(about.sys, "platform", "win32")
    monkeypatch.setattr(about, "icon_path", lambda ext: "quodeq.ico")
    monkeypatch.setattr(ctypes, "windll", _Raising(), raising=False)
    messages: list[str] = []
    monkeypatch.setattr(about, "log_debug", messages.append)
    about.set_app_icon()
    assert any("windows taskbar icon not set" in m for m in messages)


def test_kill_api_logs_when_process_is_already_gone(monkeypatch) -> None:
    def _raise(*_a, **_k):
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(native_ops.os, "kill", _raise)
    with patch.object(native_ops._logger, "debug") as debug:
        native_ops.kill_api(424242)  # signature: kill_api(pid: int) -> None
    assert debug.called
    assert "already gone" in debug.call_args.args[0]


def test_sync_fullscreen_observer_logs_attribute_error() -> None:
    pytest.importorskip("AppKit", reason="macOS-only fullscreen observer")

    class _BrokenWindow:
        def __getattr__(self, name):
            raise AttributeError(name)

    with patch.object(fullscreen._logger, "debug") as debug:
        fullscreen._sync_fullscreen_observer(_BrokenWindow(), None)  # signature: (window: object, nswindow: object) -> None
    assert debug.called
    assert "observer sync failed" in debug.call_args.args[0]


def test_shutdown_logs_when_socket_close_fails(tmp_path) -> None:
    controller = instance.InstanceController(tmp_path / "test.sock")

    class _FakeSock:
        def close(self):
            raise OSError("bad file descriptor")

    controller._server_sock = _FakeSock()
    with patch.object(instance._logger, "debug") as debug:
        controller.shutdown()  # signature: shutdown(self) -> None
    assert debug.called
    assert "instance shutdown cleanup failed" in debug.call_args.args[0]


def test_wait_for_process_logs_once_across_multiple_timeouts(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(_process, "log_debug", messages.append)

    class _FakeProcess:
        def __init__(self) -> None:
            self._poll_calls = 0

        def poll(self):
            self._poll_calls += 1
            return None if self._poll_calls <= 2 else 0

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("x", 1)

    _process.wait_for_process(_FakeProcess())  # signature: (proc: subprocess.Popen) -> None
    # Two TimeoutExpired pacing iterations must yield exactly one debug log.
    assert len(messages) == 1
    assert "still running after" in messages[0]


@pytest.mark.skipif(os.name == "nt", reason="SIGTSTP/SIGCONT are POSIX-only")
def test_handle_tstp_logs_when_sigcont_kill_fails(monkeypatch) -> None:
    def _raise(*_a, **_k):
        raise OSError("no such process")

    monkeypatch.setattr(server.os, "kill", _raise)
    handler = server._make_tstp_handler(lambda: None)
    with patch.object(server._logger, "debug") as debug:
        with pytest.raises(SystemExit):
            handler(0, None)  # signature: _handle_tstp(_signum, _frame) -> None
    assert debug.called
    assert "SIGTSTP handling failed" in debug.call_args.args[0]


def test_serve_blocking_logs_on_keyboard_interrupt() -> None:
    mock_proc = MagicMock()
    mock_stop = MagicMock()
    with patch.object(server, "wait_for_process", side_effect=KeyboardInterrupt):
        with patch.object(server._logger, "debug") as debug:
            server._serve_blocking(mock_proc, mock_stop)
    mock_stop.assert_called_once()
    assert debug.called
    assert "KeyboardInterrupt" in debug.call_args.args[0]


def test_send_token_logs_on_write_failure() -> None:
    window_proc = MagicMock()
    window_proc.stdin.write.side_effect = ValueError("bad token")
    with patch.object(webview_token._logger, "debug") as debug:
        webview_token._send_token(window_proc)  # signature: (window_proc: subprocess.Popen | None) -> None
    assert debug.called
    assert "webview token handoff failed" in debug.call_args.args[0]


@pytest.mark.parametrize("exc", [OSError("already closed"), ValueError("closed pipe")])
def test_send_token_logs_close_failure_instead_of_swallowing_it(exc) -> None:
    """R-FT-7 -- the finally-block close() used to be a silent
    contextlib.suppress(OSError, ValueError); a failed close is now logged,
    and the write having already succeeded, close() must still be attempted."""
    window_proc = MagicMock()
    window_proc.stdin.close.side_effect = exc
    with patch.object(webview_token._logger, "debug") as debug:
        webview_token._send_token(window_proc)  # must not raise
    assert debug.called
    assert "stdin close failed" in debug.call_args.args[0]


def test_apply_macos_fullscreen_chrome_logs_toolbar_failure(monkeypatch) -> None:
    class _FakeNative:
        def setToolbar_(self, _value):
            raise AttributeError("no toolbar")

    class _FakeWindow:
        native = _FakeNative()

    monkeypatch.setattr(webview_window, "set_macos_fullscreen_class", lambda *_a, **_k: None)
    with patch.object(webview_window._logger, "debug") as debug:
        webview_window.apply_macos_fullscreen_chrome(_FakeWindow(), True)
    assert debug.called
    assert "fullscreen chrome not applied" in debug.call_args.args[0]
