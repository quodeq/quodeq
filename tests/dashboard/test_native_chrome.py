"""Native-chrome window: creation args, custom UA, and marker drift guard."""
import inspect

from unittest.mock import MagicMock, patch

import webview as real_webview

from quodeq.dashboard import _webview_window as ww


class TestWindowCreation:
    def _kwargs_for_platform(self, platform):
        with patch.object(ww.sys, "platform", platform), patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", MagicMock())
        wv.create_window.assert_called_once()
        return wv.create_window.call_args.kwargs

    def test_frameless_on_macos_for_unified_titlebar(self):
        # macOS goes frameless so NSFullSizeContentView lets the topbar run
        # under the titlebar (the unified look).
        assert self._kwargs_for_platform("darwin")["frameless"] is True

    def test_native_chrome_off_macos(self):
        assert self._kwargs_for_platform("win32")["frameless"] is False
        assert self._kwargs_for_platform("linux")["frameless"] is False

    def test_easy_drag_disabled(self):
        # Only the topbar (pywebview-drag-region) drags the window.
        assert self._kwargs_for_platform("darwin")["easy_drag"] is False

    def test_js_api_bound(self):
        api = MagicMock()
        with patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", api)
        assert wv.create_window.call_args.kwargs["js_api"] is api

    def test_create_window_only_passes_supported_kwargs(self):
        """Guard against passing a kwarg the installed pywebview's
        create_window does not accept. user_agent, for example, belongs to
        webview.start(), not create_window() — passing it here crashes the
        window process at launch (a MagicMock would silently accept it, so
        we check against the real signature)."""
        captured = {}
        with patch.object(ww, "webview") as wv:
            wv.create_window.side_effect = lambda *a, **k: captured.update(k) or MagicMock()
            ww._create_window("http://127.0.0.1:7863", MagicMock())
        allowed = set(inspect.signature(real_webview.create_window).parameters)
        unsupported = set(captured) - allowed
        assert not unsupported, f"create_window kwargs not supported by pywebview: {unsupported}"

    def test_webview_user_agent_is_a_start_kwarg(self):
        """The marker UA must be delivered via webview.start(user_agent=...);
        confirm the installed pywebview's start() accepts it."""
        assert "user_agent" in inspect.signature(real_webview.start).parameters


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


class TestMacTrafficLights:
    def test_unhides_three_buttons_on_macos(self):
        from PyObjCTools import AppHelper
        nswindow = MagicMock()
        window = MagicMock()
        window.native = nswindow
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()):
            ww._show_macos_traffic_lights(window)
        # one standardWindowButton_ lookup per traffic light (0,1,2), each un-hidden
        assert nswindow.standardWindowButton_.call_count == 3
        setter = nswindow.standardWindowButton_.return_value.setHidden_
        assert setter.call_count == 3
        assert all(c.args == (False,) for c in setter.call_args_list)

    def test_noop_without_native_handle(self):
        from PyObjCTools import AppHelper
        window = MagicMock()
        window.native = None
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()) as ca:
            ww._show_macos_traffic_lights(window)
        ca.assert_not_called()


class TestMacAppIdentityIdempotent:
    def test_calling_twice_does_not_raise(self):
        # Re-defining the _AboutHandler ObjC class raised objc.error and
        # aborted _on_loaded before the traffic lights were shown. The
        # one-time install guard must make repeat calls safe. (No-op off
        # macOS, where AppKit isn't importable.)
        ww._set_macos_app_identity()
        ww._set_macos_app_identity()  # must not raise


class _SyncThread:
    """Stand-in for threading.Thread that runs the target inline on start()."""
    def __init__(self, target=None, daemon=None, **_):  # noqa: ARG002
        self._target = target

    def start(self):
        if self._target:
            self._target()


class TestMacFullscreenClass:
    def test_toggle_true_adds_class(self):
        window = MagicMock()
        with patch.object(ww.threading, "Thread", _SyncThread):
            ww._set_macos_fullscreen_class(window, True)
        window.evaluate_js.assert_called_once()
        js = window.evaluate_js.call_args.args[0]
        assert "macos-fullscreen" in js
        assert js.endswith("true)")

    def test_toggle_false_removes_class(self):
        window = MagicMock()
        with patch.object(ww.threading, "Thread", _SyncThread):
            ww._set_macos_fullscreen_class(window, False)
        js = window.evaluate_js.call_args.args[0]
        assert js.endswith("false)")

    def test_evaluate_runs_off_the_main_thread(self):
        # evaluate_js on the AppKit main thread deadlocks, so the toggle must
        # always be dispatched to a worker thread.
        window = MagicMock()
        with patch.object(ww.threading, "Thread") as thread_cls:
            ww._set_macos_fullscreen_class(window, True)
        thread_cls.assert_called_once()
        thread_cls.return_value.start.assert_called_once()
        window.evaluate_js.assert_not_called()  # only the worker calls it


class TestMacFullscreenObserver:
    def test_noop_off_macos(self):
        from PyObjCTools import AppHelper
        window = MagicMock()
        window.native = MagicMock()
        with patch.object(ww.sys, "platform", "win32"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()) as ca:
            ww._install_macos_fullscreen_observer(window)
        ca.assert_not_called()

    def test_noop_without_native_handle(self):
        from PyObjCTools import AppHelper
        window = MagicMock()
        window.native = None
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()) as ca:
            ww._install_macos_fullscreen_observer(window)
        ca.assert_not_called()

    def test_install_twice_does_not_raise(self):
        # The ObjC handler class may only be defined once per process;
        # _on_loaded calls this on every (re)load, so repeat calls must not
        # raise. (No-op off macOS, where AppKit isn't importable.)
        from PyObjCTools import AppHelper
        window = MagicMock()
        window.native = MagicMock()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()):
            ww._install_macos_fullscreen_observer(window)
            ww._install_macos_fullscreen_observer(window)  # must not raise
