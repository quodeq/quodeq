"""Tests for quodeq.dashboard._server — server lifecycle, API startup, serve modes."""

from __future__ import annotations

import signal
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from quodeq.dashboard._probes import ApiProbes


class TestEnsureActionApi:
    def test_reuses_existing_healthy_api(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: True,
            is_port_open=lambda *_a: True,
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, probes=probes)
        assert url == "http://127.0.0.1:8000"
        assert proc is None

    def test_spawns_new_api(self):
        from quodeq.dashboard._server import _ensure_action_api
        spawn = MagicMock(return_value=("http://127.0.0.1:8000", MagicMock()))
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            is_port_open=lambda *_a: False,
            spawn=spawn,
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, probes=probes)
        assert url == "http://127.0.0.1:8000"
        spawn.assert_called_once()

    def test_skips_unhealthy_port_tries_next(self):
        from quodeq.dashboard._server import _ensure_action_api
        # Port 8000 is open but unhealthy, port 7863 is closed so it spawns
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: False,
            is_port_open=MagicMock(side_effect=[True, False]),
            spawn=lambda *_a, **_k: ("http://127.0.0.1:7863", MagicMock()),
        )
        url, proc = _ensure_action_api("127.0.0.1", 8000, max_tries=2, probes=probes)
        assert "7863" in url

    def test_raises_when_no_free_port(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1", "localhost"},
            api_healthy=lambda *_a: False,
            is_port_open=lambda *_a: True,
        )
        with pytest.raises(RuntimeError, match="Unable to find a free port"):
            _ensure_action_api("127.0.0.1", 8000, max_tries=2, probes=probes)

    def test_rejects_non_localhost_without_tls(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(local_hosts=lambda *a, **k: {"127.0.0.1"})
        with patch("quodeq.dashboard._server._allow_plaintext_http", return_value=False):
            with pytest.raises(RuntimeError, match="Plaintext HTTP"):
                _ensure_action_api("192.168.1.100", 8000, probes=probes)

    def test_allows_non_localhost_with_opt_in(self):
        from quodeq.dashboard._server import _ensure_action_api
        probes = ApiProbes(
            local_hosts=lambda *a, **k: {"127.0.0.1"},
            is_port_open=lambda *_a: False,
            spawn=lambda *_a, **_k: ("http://192.168.1.100:8000", MagicMock()),
        )
        with patch("quodeq.dashboard._server._allow_plaintext_http", return_value=True):
            url, proc = _ensure_action_api("192.168.1.100", 8000, probes=probes)
        assert "192.168.1.100" in url


class TestEnsureActionApiForced:
    def test_reuses_healthy(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(api_healthy=lambda *_a: True, is_port_open=lambda *_a: True)
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)
        assert url == "http://127.0.0.1:5000"
        assert proc is None

    def test_raises_when_port_in_use_not_healthy(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(api_healthy=lambda *_a: False, is_port_open=lambda *_a: True)
        with pytest.raises(RuntimeError, match="Port 5000"):
            _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)

    def test_spawns_when_port_free(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        probes = ApiProbes(
            is_port_open=lambda *_a: False,
            spawn=lambda *_a, **_k: ("http://127.0.0.1:5000", MagicMock()),
        )
        url, proc = _ensure_action_api_forced("127.0.0.1", 5000, probes=probes)
        assert url == "http://127.0.0.1:5000"

    def test_passes_static_and_eval_dirs(self):
        from quodeq.dashboard._server import _ensure_action_api_forced
        spawn = MagicMock(return_value=("http://127.0.0.1:5000", MagicMock()))
        probes = ApiProbes(is_port_open=lambda *_a: False, spawn=spawn)
        _ensure_action_api_forced(
            "127.0.0.1", 5000, static_dist=Path("/static"), evaluations_dir="/evals", probes=probes,
        )
        args = spawn.call_args
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

    @patch("quodeq.dashboard._server._linux_webview_backend_available", return_value=True)
    @patch("quodeq.dashboard._server.subprocess.Popen")
    @patch("quodeq.dashboard._server.subprocess_cmd", return_value=["quodeq-webview"])
    def test_cold_start_launches_window(self, mock_cmd, mock_popen, mock_backend):
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = False
        mock_instance._sock_path = Path("/tmp/test.sock")

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", mock_proc, mock_stop)

        mock_popen.assert_called_once()

    @patch("quodeq.dashboard._server._linux_webview_backend_available", return_value=True)
    @patch("quodeq.dashboard._server.subprocess.Popen")
    @patch("quodeq.dashboard._server.subprocess_cmd", return_value=["quodeq-webview"])
    def test_parent_never_owns_the_reload_socket(self, mock_cmd, mock_popen, mock_backend):
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

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", mock_proc, MagicMock())

        mock_instance.try_acquire.assert_not_called()
        mock_instance.start_listening.assert_not_called()
        mock_instance.shutdown.assert_not_called()

    @patch("quodeq.dashboard._server._linux_webview_backend_available", return_value=True)
    @patch("quodeq.dashboard._server.subprocess.Popen")
    def test_focuses_existing_instead_of_retargeting_it(self, mock_popen, mock_backend):
        """The running window keeps its own backend.

        stop_children kills the API this launch spawned, so sending that URL
        would hand the window a server about to die.
        """
        from quodeq.dashboard._server import _serve_native
        mock_instance = MagicMock()
        mock_instance.probe_existing.return_value = True
        mock_instance.send_focus.return_value = None
        mock_stop = MagicMock()

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", MagicMock(), mock_stop)

        mock_instance.send_focus.assert_called_once_with()
        mock_instance.send_reload.assert_not_called()
        mock_stop.assert_called_once()
        mock_popen.assert_not_called()

    def test_webview_import_error(self):
        from quodeq.dashboard._server import _serve_native
        mock_stop = MagicMock()

        with patch.dict("sys.modules", {"webview": None}):
            with pytest.raises((RuntimeError, ImportError)):
                _serve_native("http://localhost:8000", MagicMock(), mock_stop)

    @patch("quodeq.dashboard._server._linux_webview_backend_available", return_value=True)
    @patch("quodeq.dashboard._server.subprocess.Popen")
    @patch("quodeq.dashboard._server.subprocess_cmd", return_value=["quodeq-webview"])
    @pytest.mark.parametrize("failure", [ConnectionRefusedError(), OSError("refused")])
    def test_focus_failure_opens_own_window(self, mock_cmd, mock_popen, mock_backend, failure):
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

        with self._fake_webview_ctx(), \
             patch("quodeq.dashboard._instance.InstanceController", return_value=mock_instance):
            _serve_native("http://localhost:8000", mock_proc, mock_stop)

        mock_popen.assert_called_once()
        mock_instance.shutdown.assert_not_called()
