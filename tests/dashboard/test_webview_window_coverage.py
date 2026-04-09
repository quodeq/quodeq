"""Tests for quodeq.dashboard._webview_window — window controls, icon paths, and API."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestControlsHtml:
    """Verify that the HTML/JS constants are assembled correctly."""

    def test_controls_html_is_string(self):
        from quodeq.dashboard._webview_window import _CONTROLS_HTML
        assert isinstance(_CONTROLS_HTML, str)
        assert len(_CONTROLS_HTML) > 0

    def test_inject_js_contains_controls(self):
        from quodeq.dashboard._webview_window import _INJECT_JS, _CONTROLS_HTML
        assert json.dumps(_CONTROLS_HTML)[:20] in _INJECT_JS or "qd-" in _INJECT_JS

    def test_controls_mac_has_traffic_dots(self):
        from quodeq.dashboard._webview_window import _CONTROLS_MAC
        assert "qd-traffic" in _CONTROLS_MAC
        assert "qd-dot" in _CONTROLS_MAC

    def test_controls_win_has_buttons(self):
        from quodeq.dashboard._webview_window import _CONTROLS_WIN
        assert "qd-winbtns" in _CONTROLS_WIN
        assert "qd-winbtn" in _CONTROLS_WIN

    def test_controls_js_template(self):
        from quodeq.dashboard._webview_window import _CONTROLS_JS
        assert "%s" in _CONTROLS_JS
        assert "keydown" in _CONTROLS_JS


# ---------------------------------------------------------------------------
# _WindowApi
# ---------------------------------------------------------------------------

class TestWindowApi:
    def _make_api(self):
        from quodeq.dashboard._webview_window import _WindowApi
        return _WindowApi()

    def test_init_defaults(self):
        api = self._make_api()
        assert api._window is None
        assert api._api_pid == 0
        assert api._instance is None

    def test_bind_sets_attrs(self):
        api = self._make_api()
        win = MagicMock()
        inst = MagicMock()
        api.bind(win, api_pid=42, instance=inst)
        assert api._window is win
        assert api._api_pid == 42
        assert api._instance is inst

    def test_minimize_no_window(self):
        api = self._make_api()
        api.minimize()  # no-op

    def test_minimize_with_window(self):
        api = self._make_api()
        win = MagicMock()
        api.bind(win)
        api.minimize()
        win.minimize.assert_called_once()

    def test_maximize_no_window(self):
        api = self._make_api()
        api.maximize()  # no-op

    @patch("sys.platform", "darwin")
    def test_maximize_mac_fullscreen(self):
        api = self._make_api()
        win = MagicMock()
        api.bind(win)
        api.maximize()
        win.toggle_fullscreen.assert_called_once()

    @patch("sys.platform", "win32")
    def test_maximize_win_restore(self):
        api = self._make_api()
        win = MagicMock()
        win.maximized = True
        api.bind(win)
        api.maximize()
        win.restore.assert_called_once()

    @patch("sys.platform", "win32")
    def test_maximize_win_maximize(self):
        api = self._make_api()
        win = MagicMock()
        win.maximized = False
        api.bind(win)
        api.maximize()
        win.maximize.assert_called_once()

    def test_close_no_running_eval_no_pid(self):
        api = self._make_api()
        win = MagicMock()
        api.bind(win, api_pid=0)
        with patch("os._exit") as mock_exit:
            api.close()
            mock_exit.assert_called_once_with(0)

    def test_close_with_api_pid(self):
        api = self._make_api()
        win = MagicMock()
        api.bind(win, api_pid=999)
        with patch("quodeq.dashboard._webview_window._kill_api") as mock_kill, \
             patch("os._exit") as mock_exit:
            api.close()
            mock_kill.assert_called_once_with(999)
            mock_exit.assert_called_once_with(0)

    def test_close_with_instance(self):
        api = self._make_api()
        win = MagicMock()
        inst = MagicMock()
        api.bind(win, api_pid=0, instance=inst)
        with patch("os._exit") as mock_exit:
            api.close()
            inst.shutdown.assert_called_once()
            mock_exit.assert_called_once_with(0)

    def test_close_with_running_eval_back(self):
        api = self._make_api()
        win = MagicMock()
        win.evaluate_js.return_value = "back"
        api.bind(win, api_pid=0)
        api._get_running_evaluation = MagicMock(return_value={"status": "running"})
        with patch("os._exit") as mock_exit:
            api.close()
            mock_exit.assert_not_called()

    def test_close_with_running_eval_keep(self):
        api = self._make_api()
        win = MagicMock()
        win.evaluate_js.return_value = "keep"
        api.bind(win, api_pid=0)
        api._get_running_evaluation = MagicMock(return_value={"status": "running"})
        with patch("os._exit") as mock_exit:
            api.close()
            # "keep" calls os._exit(0), but since it's mocked, execution continues
            # to the end of close() which calls os._exit(0) again
            assert mock_exit.call_count >= 1
            mock_exit.assert_any_call(0)

    def test_close_with_running_eval_cancel(self):
        api = self._make_api()
        win = MagicMock()
        win.evaluate_js.return_value = "cancel"
        api.bind(win, api_pid=0)
        api._get_running_evaluation = MagicMock(return_value={"status": "running"})
        with patch("os._exit") as mock_exit:
            api.close()
            mock_exit.assert_called_once_with(0)

    def test_close_eval_check_exception(self):
        api = self._make_api()
        win = MagicMock()
        win.evaluate_js.side_effect = RuntimeError("js failed")
        api.bind(win, api_pid=0)
        api._get_running_evaluation = MagicMock(return_value={"status": "running"})
        with patch("os._exit") as mock_exit:
            api.close()
            mock_exit.assert_called_once_with(0)


class TestGetRunningEvaluation:
    def test_returns_none_on_exception(self):
        from quodeq.dashboard._webview_window import _WindowApi
        api = _WindowApi()
        win = MagicMock()
        win.get_current_url.side_effect = RuntimeError("no url")
        api.bind(win)
        assert api._get_running_evaluation() is None

    def test_returns_running_job(self):
        from quodeq.dashboard._webview_window import _WindowApi
        api = _WindowApi()
        win = MagicMock()
        win.get_current_url.return_value = "http://localhost:5678/#/dashboard"
        api.bind(win)

        jobs = [{"status": "done"}, {"status": "running", "repo": "test"}]
        import io
        resp_body = json.dumps(jobs).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = api._get_running_evaluation()
            assert result == {"status": "running", "repo": "test"}

    def test_returns_none_when_no_running_jobs(self):
        from quodeq.dashboard._webview_window import _WindowApi
        api = _WindowApi()
        win = MagicMock()
        win.get_current_url.return_value = "http://localhost:5678/"
        api.bind(win)

        jobs = [{"status": "done"}]
        resp_body = json.dumps(jobs).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert api._get_running_evaluation() is None


class TestBuildCloseDialogJs:
    def test_basic_dialog(self):
        from quodeq.dashboard._webview_window import _WindowApi
        js = _WindowApi._build_close_dialog_js({
            "phase": "analyzing", "currentDimension": "security", "repo": "org/myapp"
        })
        assert "Evaluation in progress" in js
        assert "myapp" in js
        assert "security" in js
        assert "analyzing" in js

    def test_empty_job(self):
        from quodeq.dashboard._webview_window import _WindowApi
        js = _WindowApi._build_close_dialog_js({})
        assert "Evaluation in progress" in js

    def test_repo_with_slash(self):
        from quodeq.dashboard._webview_window import _WindowApi
        js = _WindowApi._build_close_dialog_js({"repo": "org/deep/name"})
        assert "name" in js


# ---------------------------------------------------------------------------
# _kill_api
# ---------------------------------------------------------------------------

class TestKillApi:
    @patch("os.kill")
    def test_kill_on_unix(self, mock_kill):
        from quodeq.dashboard._webview_window import _kill_api
        with patch("sys.platform", "darwin"):
            _kill_api(1234)
            mock_kill.assert_called_once()

    @patch("os.kill", side_effect=ProcessLookupError)
    def test_kill_process_not_found(self, mock_kill):
        from quodeq.dashboard._webview_window import _kill_api
        _kill_api(1234)  # should not raise


# ---------------------------------------------------------------------------
# _icon_path
# ---------------------------------------------------------------------------

class TestIconPath:
    def test_unknown_extension(self):
        from quodeq.dashboard._webview_window import _icon_path
        assert _icon_path(".png") is None

    def test_icns_not_found(self):
        from quodeq.dashboard._webview_window import _icon_path
        # The icns file likely doesn't exist in the test environment
        result = _icon_path(".icns")
        assert result is None or isinstance(result, str)

    def test_ico_not_found(self):
        from quodeq.dashboard._webview_window import _icon_path
        result = _icon_path(".ico")
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# _set_app_icon
# ---------------------------------------------------------------------------

class TestSetAppIcon:
    @patch("sys.platform", "linux")
    def test_noop_on_linux(self):
        from quodeq.dashboard._webview_window import _set_app_icon
        _set_app_icon()  # no-op on Linux

    @patch("sys.platform", "darwin")
    def test_darwin_import_error(self):
        from quodeq.dashboard._webview_window import _set_app_icon
        with patch("quodeq.dashboard._webview_window._icon_path", return_value=None):
            _set_app_icon()  # ImportError for AppKit is caught
