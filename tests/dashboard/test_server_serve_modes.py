"""Tests for quodeq.dashboard._server's serve modes — browser, blocking, native.

Split out of test_server_coverage.py when that file crossed the 300-line cap;
that file keeps the API-startup (_ensure_action_api[_forced]) coverage.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestServeAndWait:
    @patch("quodeq.dashboard._server.log_success")
    @patch("quodeq.dashboard._server.webbrowser")
    def test_browser_mode_opens_browser(self, mock_browser, mock_log):
        from quodeq.dashboard._server import _serve_and_wait
        config = MagicMock()
        config.build.use_native = False
        config.build.open_browser = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0

        with patch("quodeq.dashboard._server._serve_blocking") as mock_block:
            _serve_and_wait("http://localhost:8000", mock_proc, config)
            mock_browser.open.assert_called_once_with("http://localhost:8000")
            mock_block.assert_called_once()

    @patch("quodeq.dashboard._server.log_success")
    def test_no_browser_mode(self, mock_log):
        from quodeq.dashboard._server import _serve_and_wait
        config = MagicMock()
        config.build.use_native = False
        config.build.open_browser = False

        with patch("quodeq.dashboard._server._serve_blocking") as mock_block:
            _serve_and_wait("http://localhost:8000", None, config)
            mock_block.assert_called_once()

    @patch("quodeq.dashboard._server.log_success")
    @patch("quodeq.dashboard._server._serve_native")
    def test_native_mode(self, mock_native, mock_log):
        from quodeq.dashboard._server import _serve_and_wait
        config = MagicMock()
        config.build.use_native = True
        config.build.open_browser = True
        _serve_and_wait("http://localhost:8000", MagicMock(), config)
        mock_native.assert_called_once()


class TestServeBlocking:
    def test_keyboard_interrupt(self):
        from quodeq.dashboard._server import _serve_blocking
        mock_proc = MagicMock()
        mock_stop = MagicMock()

        with patch("quodeq.dashboard._server._wait_for_process", side_effect=KeyboardInterrupt):
            _serve_blocking(mock_proc, mock_stop)
        mock_stop.assert_called_once()

    def test_no_process_unix(self):
        from quodeq.dashboard._server import _serve_blocking
        mock_stop = MagicMock()
        with patch("quodeq.dashboard._server.IS_WIN32", False), \
             patch("quodeq.dashboard._server.signal") as mock_signal:
            mock_signal.pause.side_effect = KeyboardInterrupt
            _serve_blocking(None, mock_stop)
        mock_stop.assert_called_once()

    def test_process_exits(self):
        from quodeq.dashboard._server import _serve_blocking
        mock_proc = MagicMock()
        mock_stop = MagicMock()
        with patch("quodeq.dashboard._server._wait_for_process"):
            _serve_blocking(mock_proc, mock_stop)
        mock_stop.assert_called_once()


class TestServeNative:
    """Tests for _serve_native — injects a NativeShell instead of monkeypatching."""

    @staticmethod
    def _shell(**overrides):
        from quodeq.dashboard._probes import NativeShell
        defaults = dict(webview_importable=lambda: True, linux_backend_available=lambda: True)
        defaults.update(overrides)
        return NativeShell(**defaults)

    def test_cold_start_launches_window(self):
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = False
        mock_instance._sock_path = Path("/tmp/test.sock")

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_stop = MagicMock()
        mock_popen = MagicMock()

        shell = self._shell(make_instance=lambda: mock_instance, spawn_window=mock_popen)
        _serve_native("http://localhost:8000", mock_proc, mock_stop, shell=shell)

        mock_popen.assert_called_once()

    def test_parent_never_owns_the_reload_socket(self):
        """The window process owns the socket, so the parent must not bind it.

        Binding here is what left the webview child unable to acquire: its
        listener thread died on the unbound socket and every relaunch's reload
        was dropped. Probing must also never unlink a live instance's socket.
        """
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = False
        mock_instance._sock_path = Path("/tmp/test.sock")

        mock_proc = MagicMock()
        mock_proc.pid = 1234

        shell = self._shell(make_instance=lambda: mock_instance, spawn_window=MagicMock())
        _serve_native("http://localhost:8000", mock_proc, MagicMock(), shell=shell)

        mock_instance.try_acquire.assert_not_called()
        mock_instance.start_listening.assert_not_called()
        mock_instance.shutdown.assert_not_called()

    def test_focuses_existing_instead_of_retargeting_it(self):
        """The running window keeps its own backend.

        stop_children kills the API this launch spawned, so sending that URL
        would hand the window a server about to die.
        """
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = True
        mock_instance.send_focus.return_value = None
        mock_stop = MagicMock()
        mock_popen = MagicMock()

        shell = self._shell(make_instance=lambda: mock_instance, spawn_window=mock_popen)
        _serve_native("http://localhost:8000", MagicMock(), mock_stop, shell=shell)

        mock_instance.send_focus.assert_called_once_with()
        mock_instance.send_reload.assert_not_called()
        mock_stop.assert_called_once()
        mock_popen.assert_not_called()

    def test_webview_import_error(self):
        from quodeq.dashboard._server import _serve_native
        mock_stop = MagicMock()

        shell = self._shell(webview_importable=lambda: False)
        with pytest.raises((RuntimeError, ImportError)):
            _serve_native("http://localhost:8000", MagicMock(), mock_stop, shell=shell)

    @pytest.mark.parametrize("failure", [ConnectionRefusedError(), OSError("refused")])
    def test_focus_failure_opens_own_window(self, failure):
        """An instance that answers the probe but dies before the send.

        The launch must still produce a window rather than exiting silently —
        the child's own try_acquire clears the now-stale socket.
        """
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = True
        mock_instance.send_focus.side_effect = failure
        mock_instance._sock_path = Path("/tmp/test.sock")

        mock_proc = MagicMock()
        mock_proc.pid = 999
        mock_stop = MagicMock()
        mock_popen = MagicMock()

        shell = self._shell(make_instance=lambda: mock_instance, spawn_window=mock_popen)
        _serve_native("http://localhost:8000", mock_proc, mock_stop, shell=shell)

        mock_popen.assert_called_once()
        mock_instance.shutdown.assert_not_called()
