"""Native-chrome window: creation args, custom UA, and marker drift guard."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww


class TestWindowCreation:
    def test_create_window_uses_native_chrome_and_webview_ua(self):
        api = MagicMock()
        with patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", api)
        wv.create_window.assert_called_once()
        kwargs = wv.create_window.call_args.kwargs
        assert kwargs["frameless"] is False
        assert ww._WEBVIEW_UA_MARKER in kwargs["user_agent"]
        assert kwargs["js_api"] is api


class TestUaMarkerNoDrift:
    def test_marker_matches_security_module(self):
        from quodeq.api import security
        assert ww._WEBVIEW_UA_MARKER == security._WEBVIEW_UA_MARKER

    def test_user_agent_carries_marker(self):
        assert ww._WEBVIEW_UA_MARKER in ww._webview_user_agent()


class TestSetTitlebarTheme:
    def _api(self):
        api = ww._WindowApi()
        api._window = MagicMock()
        return api

    def test_dark_dispatches_macos(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(ww, "_set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("dark")
        mac.assert_called_once_with(api._window, True)

    def test_light_dispatches_macos(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(ww, "_set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("light")
        mac.assert_called_once_with(api._window, False)

    def test_dark_dispatches_windows(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "win32"), \
             patch.object(ww, "_set_windows_titlebar") as win:
            api.set_titlebar_theme("dark")
        win.assert_called_once_with(True)

    def test_unknown_mode_is_noop(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(ww, "_set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("purple")
        mac.assert_not_called()


class TestOnClosing:
    def _wire(self, job, confirm=True):
        api = MagicMock()
        api._get_running_evaluation.return_value = job
        window = MagicMock()
        window.create_confirmation_dialog.return_value = confirm
        return ww._make_on_closing(api, window), window

    def test_no_job_closes_without_dialog(self):
        on_closing, window = self._wire(job=None)
        assert on_closing() is True
        window.create_confirmation_dialog.assert_not_called()

    def test_running_job_confirm_allows_close(self):
        on_closing, window = self._wire(job={"jobId": "x"}, confirm=True)
        assert on_closing() is True
        window.create_confirmation_dialog.assert_called_once()

    def test_running_job_cancel_blocks_close(self):
        on_closing, window = self._wire(job={"jobId": "x"}, confirm=False)
        assert on_closing() is False
