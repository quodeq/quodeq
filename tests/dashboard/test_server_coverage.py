"""Tests for quodeq.dashboard._server — server lifecycle, API startup, serve modes."""

from __future__ import annotations

import signal
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


class TestEnsureActionApi:
    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1", "localhost"})
    @patch("quodeq.dashboard._server.action_api_healthy", return_value=True)
    @patch("quodeq.dashboard._server._is_port_open", return_value=True)
    def test_reuses_existing_healthy_api(self, mock_port, mock_healthy, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        url, proc = _ensure_action_api("127.0.0.1", 8000)
        assert url == "http://127.0.0.1:8000"
        assert proc is None

    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1", "localhost"})
    @patch("quodeq.dashboard._server._spawn_and_wait_local", return_value=("http://127.0.0.1:8000", MagicMock()))
    @patch("quodeq.dashboard._server._is_port_open", return_value=False)
    def test_spawns_new_api(self, mock_port, mock_spawn, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        url, proc = _ensure_action_api("127.0.0.1", 8000)
        assert url == "http://127.0.0.1:8000"
        mock_spawn.assert_called_once()

    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1", "localhost"})
    @patch("quodeq.dashboard._server.action_api_healthy", return_value=False)
    @patch("quodeq.dashboard._server._is_port_open", return_value=True)
    @patch("quodeq.dashboard._server._spawn_and_wait_local", return_value=("http://127.0.0.1:8001", MagicMock()))
    def test_skips_unhealthy_port_tries_next(self, mock_spawn, mock_port, mock_healthy, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        # Port 8000 is open but unhealthy, port 8001 is closed so it spawns
        mock_port.side_effect = [True, False]
        url, proc = _ensure_action_api("127.0.0.1", 8000, max_tries=2)
        assert "8001" in url

    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1", "localhost"})
    @patch("quodeq.dashboard._server.action_api_healthy", return_value=False)
    @patch("quodeq.dashboard._server._is_port_open", return_value=True)
    def test_raises_when_no_free_port(self, mock_port, mock_healthy, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        with pytest.raises(RuntimeError, match="Unable to find a free port"):
            _ensure_action_api("127.0.0.1", 8000, max_tries=2)

    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1"})
    @patch("quodeq.dashboard._server._allow_plaintext_http", return_value=False)
    def test_rejects_non_localhost_without_tls(self, mock_allow, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        with pytest.raises(RuntimeError, match="Plaintext HTTP"):
            _ensure_action_api("192.168.1.100", 8000)

    @patch("quodeq.dashboard._server._local_hosts", return_value={"127.0.0.1"})
    @patch("quodeq.dashboard._server._allow_plaintext_http", return_value=True)
    @patch("quodeq.dashboard._server._spawn_and_wait_local", return_value=("http://192.168.1.100:8000", MagicMock()))
    @patch("quodeq.dashboard._server._is_port_open", return_value=False)
    def test_allows_non_localhost_with_opt_in(self, mock_port, mock_spawn, mock_allow, mock_hosts):
        from quodeq.dashboard._server import _ensure_action_api
        url, proc = _ensure_action_api("192.168.1.100", 8000)
        assert "192.168.1.100" in url


class TestEnsureActionApiForced:
    @patch("quodeq.dashboard._server.action_api_healthy", return_value=True)
    @patch("quodeq.dashboard._server._is_port_open", return_value=True)
    def test_reuses_healthy(self, mock_port, mock_healthy):
        from quodeq.dashboard._server import _ensure_action_api_forced
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000)
        assert url == "http://127.0.0.1:5000"
        assert proc is None

    @patch("quodeq.dashboard._server.action_api_healthy", return_value=False)
    @patch("quodeq.dashboard._server._is_port_open", return_value=True)
    def test_raises_when_port_in_use_not_healthy(self, mock_port, mock_healthy):
        from quodeq.dashboard._server import _ensure_action_api_forced
        with pytest.raises(RuntimeError, match="Port 5000"):
            _ensure_action_api_forced("127.0.0.1", 5000)

    @patch("quodeq.dashboard._server._spawn_and_wait_local", return_value=("http://127.0.0.1:5000", MagicMock()))
    @patch("quodeq.dashboard._server._is_port_open", return_value=False)
    def test_spawns_when_port_free(self, mock_port, mock_spawn):
        from quodeq.dashboard._server import _ensure_action_api_forced
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000)
        assert url == "http://127.0.0.1:5000"

    @patch("quodeq.dashboard._server._spawn_and_wait_local", return_value=("http://127.0.0.1:5000", MagicMock()))
    @patch("quodeq.dashboard._server._is_port_open", return_value=False)
    def test_passes_static_and_eval_dirs(self, mock_port, mock_spawn):
        from quodeq.dashboard._server import _ensure_action_api_forced
        _ensure_action_api_forced("127.0.0.1", 5000, static_dist=Path("/static"), evaluations_dir="/evals")
        args = mock_spawn.call_args
        assert args[0][1] == "http://127.0.0.1:5000"


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
    """Tests for _serve_native — requires mocking webview import and InstanceController."""

    @staticmethod
    def _fake_webview_ctx():
        """Context manager that makes 'import webview' succeed."""
        import types
        fake = types.ModuleType("webview")
        return patch.dict("sys.modules", {"webview": fake})

    @patch("quodeq.dashboard._server.subprocess.Popen")
    @patch("quodeq.dashboard._server.subprocess_cmd", return_value=["quodeq-webview"])
    def test_acquires_and_launches(self, mock_cmd, mock_popen):
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.try_acquire.return_value = True
        mock_instance._sock_path = Path("/tmp/test.sock")

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", mock_proc, mock_stop)

        mock_popen.assert_called_once()

    @patch("quodeq.dashboard._server.subprocess.Popen")
    def test_send_reload_to_existing(self, mock_popen):
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.try_acquire.return_value = False
        mock_instance.send_reload.return_value = None
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", MagicMock(), mock_stop)

        mock_instance.send_reload.assert_called_once_with("http://localhost:8000")
        mock_stop.assert_called_once()
        mock_popen.assert_not_called()

    def test_webview_import_error(self):
        from quodeq.dashboard._server import _serve_native
        mock_stop = MagicMock()

        with patch.dict("sys.modules", {"webview": None}):
            with pytest.raises((RuntimeError, ImportError)):
                _serve_native("http://localhost:8000", MagicMock(), mock_stop)

    @patch("quodeq.dashboard._server.subprocess.Popen")
    @patch("quodeq.dashboard._server.subprocess_cmd", return_value=["quodeq-webview"])
    def test_reload_fails_opens_new(self, mock_cmd, mock_popen):
        from quodeq.dashboard._server import _serve_native
        mock_instance1 = MagicMock()
        mock_instance1.try_acquire.return_value = False
        mock_instance1.send_reload.side_effect = ConnectionRefusedError()
        mock_instance1._sock_path = Path("/tmp/test.sock")

        mock_instance2 = MagicMock()
        mock_instance2.try_acquire.return_value = True
        mock_instance2._sock_path = Path("/tmp/test.sock")

        instances = [mock_instance1, mock_instance2]

        mock_proc = MagicMock()
        mock_proc.pid = 999
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", side_effect=instances):
            _serve_native("http://localhost:8000", mock_proc, mock_stop)

        mock_instance1.shutdown.assert_called_once()
        mock_popen.assert_called_once()

    @patch("quodeq.dashboard._server.subprocess.Popen")
    def test_reload_fails_second_acquire_fails(self, mock_popen):
        """When reload fails and second acquire also fails, stop_children is called."""
        from quodeq.dashboard._server import _serve_native
        mock_instance1 = MagicMock()
        mock_instance1.try_acquire.return_value = False
        mock_instance1.send_reload.side_effect = OSError("refused")

        mock_instance2 = MagicMock()
        mock_instance2.try_acquire.return_value = False

        instances = [mock_instance1, mock_instance2]
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", side_effect=instances):
            _serve_native("http://localhost:8000", MagicMock(), mock_stop)

        mock_stop.assert_called_once()
        mock_popen.assert_not_called()
