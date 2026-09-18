"""macOS native chrome: traffic lights, app identity, fullscreen chrome/observer and exception logging."""
from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard import _webview_window_chrome as chrome
from tests.dashboard._native_chrome_helpers import _MACOS_ONLY


@_MACOS_ONLY
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
        with patch("threading.Thread", _SyncThread):
            ww._set_macos_fullscreen_class(window, True)
        window.evaluate_js.assert_called_once()
        js = window.evaluate_js.call_args.args[0]
        assert "macos-fullscreen" in js
        assert js.endswith("true)")

    def test_toggle_false_removes_class(self):
        window = MagicMock()
        with patch("threading.Thread", _SyncThread):
            ww._set_macos_fullscreen_class(window, False)
        js = window.evaluate_js.call_args.args[0]
        assert js.endswith("false)")

    def test_evaluate_runs_off_the_main_thread(self):
        # evaluate_js on the AppKit main thread deadlocks, so the toggle must
        # always be dispatched to a worker thread.
        window = MagicMock()
        with patch("threading.Thread") as thread_cls:
            ww._set_macos_fullscreen_class(window, True)
        thread_cls.assert_called_once()
        thread_cls.return_value.start.assert_called_once()
        window.evaluate_js.assert_not_called()  # only the worker calls it


class TestMacFullscreenChrome:
    def test_fullscreen_drops_toolbar(self):
        # macOS draws the unified toolbar as an empty gray bar at the top in
        # fullscreen — drop it (the lights it centers are hidden there anyway).
        window = MagicMock()
        nswindow = window.native
        with patch("threading.Thread", _SyncThread), \
             patch.object(chrome, "_apply_unified_toolbar") as restore:
            ww._apply_macos_fullscreen_chrome(window, True)
        nswindow.setToolbar_.assert_called_once_with(None)
        restore.assert_not_called()
        assert window.evaluate_js.call_args.args[0].endswith("true)")

    def test_windowed_restores_toolbar(self):
        window = MagicMock()
        nswindow = window.native
        with patch("threading.Thread", _SyncThread), \
             patch.object(chrome, "_apply_unified_toolbar") as restore:
            ww._apply_macos_fullscreen_chrome(window, False)
        restore.assert_called_once_with(nswindow)
        nswindow.setToolbar_.assert_not_called()
        assert window.evaluate_js.call_args.args[0].endswith("false)")

    def test_load_sync_does_not_re_add_toolbar(self):
        # The initial install owns the windowed toolbar; the load-time sync
        # must not add a second one (restore_toolbar=False).
        window = MagicMock()
        nswindow = window.native
        with patch("threading.Thread", _SyncThread), \
             patch.object(chrome, "_apply_unified_toolbar") as restore:
            ww._apply_macos_fullscreen_chrome(window, False, restore_toolbar=False)
        restore.assert_not_called()
        nswindow.setToolbar_.assert_not_called()
        assert window.evaluate_js.call_args.args[0].endswith("false)")


@_MACOS_ONLY
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


@_MACOS_ONLY
class TestNativeChromeLogging:
    """Verify that native chrome functions log exceptions instead of silently swallowing them."""

    def test_traffic_lights_logs_on_exception(self, caplog):
        import logging
        from PyObjCTools import AppHelper

        window = MagicMock()
        window.native = MagicMock()
        window.native.standardWindowButton_.side_effect = AttributeError("button not found")

        with patch.object(chrome.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()):
            with caplog.at_level(logging.DEBUG, logger="quodeq.dashboard._webview_window_chrome"):
                chrome._show_macos_traffic_lights(window)
        assert "traffic light visibility toggle failed" in caplog.text

    def test_unified_toolbar_logs_on_exception(self, caplog):
        import logging
        from PyObjCTools import AppHelper

        window = MagicMock()
        window.native = MagicMock()

        # Make _apply_unified_toolbar raise
        with patch.object(chrome.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()), \
             patch.object(chrome, "_apply_unified_toolbar", side_effect=TypeError("toolbar error")):
            with caplog.at_level(logging.DEBUG, logger="quodeq.dashboard._webview_window_chrome"):
                chrome._set_macos_unified_toolbar(window)
        assert "unified toolbar installation failed" in caplog.text

    def test_titlebar_appearance_logs_on_exception(self, caplog):
        import logging
        from PyObjCTools import AppHelper

        window = MagicMock()
        window.native = MagicMock()
        # Make setAppearance_ raise to trigger the except block
        window.native.setAppearance_.side_effect = AttributeError("appearance not available")

        with patch.object(chrome.sys, "platform", "darwin"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()):
            with caplog.at_level(logging.DEBUG, logger="quodeq.dashboard._webview_window_chrome"):
                chrome._set_macos_titlebar_appearance(window, dark=True)
        assert "titlebar appearance toggle failed" in caplog.text

    def test_windows_titlebar_logs_on_exception(self, caplog):
        import logging

        # On non-Windows, ctypes.windll doesn't exist, triggering AttributeError
        # which lands in the except (AttributeError, OSError) clause
        with patch.object(chrome.sys, "platform", "win32"):
            with caplog.at_level(logging.DEBUG, logger="quodeq.dashboard._webview_window_chrome"):
                chrome._set_windows_titlebar(dark=True)
        assert "Windows titlebar DWM configuration failed" in caplog.text
