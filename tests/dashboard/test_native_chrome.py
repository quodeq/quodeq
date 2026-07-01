"""Native-chrome window: creation args, custom UA, and marker drift guard."""
import inspect
import sys

from unittest.mock import MagicMock, patch

import pytest
import webview as real_webview

from quodeq.dashboard import _webview_window as ww

# Some tests import PyObjCTools to patch AppHelper. pyobjc is darwin-only
# (pywebview pulls it in under sys_platform == 'darwin'), so those tests can
# only run on macOS — they would ModuleNotFoundError on Linux/Windows CI.
_MACOS_ONLY = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="exercises macOS AppKit/PyObjC native chrome; pyobjc is darwin-only",
)


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
    """The close handler behaves differently by backend (see _make_on_closing):

    macOS/GTK/Qt marshal the dialog onto the GUI thread and block the caller, so
    it must run OFF the GUI thread (worker + veto + destroy). Windows/winforms
    shows a direct modal MessageBox and runs its closing handler on the UI
    thread, so it shows the dialog inline. macOS shows a 3-button alert (keep
    scanning / cancel scan / stay); other backends show a 2-button dialog (OK =
    keep scanning, Cancel = stay). Tests pin the platform explicitly so they are
    deterministic regardless of the host OS, and patch the choice seam so no
    real native alert is shown.
    """

    def _wire(self, job, platform="darwin"):
        api = MagicMock()
        api._get_running_evaluation.return_value = job
        window = MagicMock()
        with patch.object(ww.sys, "platform", platform):
            on_closing = ww._make_on_closing(api, window)
        return on_closing, window, api

    @staticmethod
    def _join(on_closing):
        worker = getattr(on_closing, "_worker", None)
        if worker is not None:
            worker.join(timeout=2)
            # A hung worker is the exact failure class this fix targets — surface
            # it as itself, not as a downstream mock-call-count mismatch.
            assert not worker.is_alive(), "close-confirm worker did not finish (possible re-deadlock)"

    # --- async (macOS / GTK / Qt): dialog runs off the GUI thread -----------

    def test_no_job_closes_without_prompt(self):
        on_closing, window, api = self._wire(job=None)
        with patch.object(ww, "_ask_close_choice") as choose:
            assert on_closing() is True
        choose.assert_not_called()

    def test_running_job_vetoes_the_close_and_prompts_async(self):
        # A running scan must NOT be answered synchronously: the native dialog
        # marshals onto the GUI thread and blocks its caller, so answering from
        # the closing handler (which runs ON the GUI thread) self-deadlocks. The
        # handler vetoes this close and shows the dialog on a worker thread.
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(ww, "_ask_close_choice", return_value="stay") as choose:
            assert on_closing() is False
            self._join(on_closing)
        choose.assert_called_once()

    def test_dialog_runs_off_the_calling_thread(self):
        import threading
        caller = threading.get_ident()
        seen = {}
        on_closing, window, api = self._wire(job={"jobId": "x"})

        def _choose(_w):
            seen["tid"] = threading.get_ident()
            return "stay"

        with patch.object(ww, "_ask_close_choice", side_effect=_choose):
            assert on_closing() is False
            self._join(on_closing)
        assert seen["tid"] != caller

    def test_on_closing_returns_without_waiting_on_the_dialog(self):
        # The core invariant of the whole fix: _on_closing must return promptly,
        # never blocking on the dialog/worker. A regression that joins the worker
        # (or answers inline) would park here and re-deadlock.
        import threading
        release = threading.Event()
        on_closing, window, api = self._wire(job={"jobId": "x"})

        def _choose(_w):
            release.wait()
            return "keep"

        with patch.object(ww, "_ask_close_choice", side_effect=_choose):
            result = []
            caller = threading.Thread(target=lambda: result.append(on_closing()))
            caller.start()
            caller.join(timeout=2)
            try:
                assert not caller.is_alive(), "_on_closing blocked on the dialog — re-deadlock regression"
                assert result == [False]
            finally:
                release.set()
                self._join(on_closing)

    def test_keep_scanning_closes_window_without_cancelling(self):
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(ww, "_ask_close_choice", return_value="keep"):
            on_closing()
            self._join(on_closing)
        window.destroy.assert_called_once()
        api._cancel_evaluation.assert_not_called()
        # The re-issued close (from destroy) is allowed straight through.
        assert on_closing() is True

    def test_cancel_scan_and_quit_cancels_then_closes(self):
        on_closing, window, api = self._wire(job={"jobId": "job-42"})
        with patch.object(ww, "_ask_close_choice", return_value="cancel"):
            on_closing()
            self._join(on_closing)
        api._cancel_evaluation.assert_called_once_with("job-42")
        window.destroy.assert_called_once()
        assert on_closing() is True

    def test_stay_keeps_window_open_and_can_reprompt(self):
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(ww, "_ask_close_choice", return_value="stay") as choose:
            assert on_closing() is False
            self._join(on_closing)
            window.destroy.assert_not_called()
            api._cancel_evaluation.assert_not_called()
            # Staying leaves the window open; a later close prompts again.
            assert on_closing() is False
            self._join(on_closing)
        assert choose.call_count == 2

    def test_double_close_while_prompting_prompts_once(self):
        # Clicking close again while the dialog is already up must not spawn a
        # second worker / second alert — the `prompting` guard covers this.
        import threading
        import time
        release = threading.Event()
        calls = []
        on_closing, window, api = self._wire(job={"jobId": "x"})

        def _choose(_w):
            calls.append(1)
            release.wait()
            return "keep"

        with patch.object(ww, "_ask_close_choice", side_effect=_choose):
            assert on_closing() is False
            first_worker = on_closing._worker
            for _ in range(200):  # wait until the worker is actually prompting
                if len(calls) == 1:
                    break
                time.sleep(0.01)
            assert len(calls) == 1
            # Second close while still prompting: vetoed, no new worker/prompt.
            assert on_closing() is False
            assert on_closing._worker is first_worker
            assert len(calls) == 1
            release.set()
            self._join(on_closing)

    def test_second_close_during_cancel_does_not_reprompt(self):
        # On 'cancel', `prompting` is held through the (possibly slow) cancel
        # call, so a second close during it must not spawn a second worker/dialog.
        import threading
        cancel_started = threading.Event()
        release = threading.Event()
        on_closing, window, api = self._wire(job={"jobId": "x"})

        def _cancel(_job_id):
            cancel_started.set()
            release.wait()

        api._cancel_evaluation.side_effect = _cancel
        with patch.object(ww, "_ask_close_choice", return_value="cancel") as choose:
            assert on_closing() is False
            first_worker = on_closing._worker
            assert cancel_started.wait(2)  # worker is now inside the cancel call
            # Second close while the cancel is in flight: vetoed, no new prompt.
            assert on_closing() is False
            assert on_closing._worker is first_worker
            assert choose.call_count == 1
            release.set()
            self._join(on_closing)
        window.destroy.assert_called_once()
        api._cancel_evaluation.assert_called_once_with("x")

    def test_dialog_error_does_not_trap_the_user(self):
        # If the choice can't be obtained, fall through to closing the window
        # (treat as 'keep') rather than leaving it un-closeable.
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(ww, "_ask_close_choice", side_effect=RuntimeError("no GUI")):
            assert on_closing() is False
            self._join(on_closing)
        window.destroy.assert_called_once()
        api._cancel_evaluation.assert_not_called()

    # --- _ask_close_choice: platform dispatch + 2-button mapping ------------

    def test_ask_close_choice_macos_dispatches_to_native_alert(self):
        window = MagicMock()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(ww, "_macos_confirm_close", return_value="cancel") as mac:
            assert ww._ask_close_choice(window) == "cancel"
        mac.assert_called_once_with(window)

    def test_ask_close_choice_non_macos_ok_is_keep(self):
        window = MagicMock()
        window.create_confirmation_dialog.return_value = True
        with patch.object(ww.sys, "platform", "linux"):
            assert ww._ask_close_choice(window) == "keep"

    def test_ask_close_choice_non_macos_cancel_is_stay(self):
        window = MagicMock()
        window.create_confirmation_dialog.return_value = False
        with patch.object(ww.sys, "platform", "linux"):
            assert ww._ask_close_choice(window) == "stay"

    def test_ask_close_choice_non_macos_dialog_error_is_keep(self):
        window = MagicMock()
        window.create_confirmation_dialog.side_effect = RuntimeError("no GUI")
        with patch.object(ww.sys, "platform", "linux"):
            assert ww._ask_close_choice(window) == "keep"

    # --- NSAlert return -> choice mapping (pure) ----------------------------

    def test_alert_return_to_choice_mapping(self):
        assert ww._alert_return_to_choice(1000, 1000, 1001) == "keep"
        assert ww._alert_return_to_choice(1001, 1000, 1001) == "cancel"
        assert ww._alert_return_to_choice(1002, 1000, 1001) == "stay"

    def test_macos_confirm_close_off_macos_is_safe_default(self):
        # macOS-only path: off darwin it must degrade without touching AppKit.
        with patch.object(ww.sys, "platform", "linux"):
            assert ww._macos_confirm_close(MagicMock()) == "keep"

    # --- _cancel_evaluation -------------------------------------------------

    def test_cancel_evaluation_issues_delete_with_origin(self):
        api = ww._WindowApi()
        api._base_url = "http://127.0.0.1:7863"
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["origin"] = req.headers.get("Origin")
            return _Resp()

        with patch.object(ww.urllib.request, "urlopen", side_effect=_fake_urlopen):
            api._cancel_evaluation("job-42")
        assert captured["url"] == "http://127.0.0.1:7863/api/evaluations/job-42"
        assert captured["method"] == "DELETE"
        assert captured["origin"] == "http://127.0.0.1:7863"

    def test_cancel_evaluation_noop_without_job_or_base_url(self):
        api = ww._WindowApi()
        with patch.object(ww.urllib.request, "urlopen") as uo:
            api._base_url = ""
            api._cancel_evaluation("job-42")   # no base url
            api._base_url = "http://x"
            api._cancel_evaluation(None)         # no job id
        uo.assert_not_called()

    def test_cancel_evaluation_swallows_urlopen_error(self):
        # Best-effort: a failed cancel must not propagate (the worker destroys
        # the window right after, so a raise would trap the user mid-close).
        import urllib.error
        api = ww._WindowApi()
        api._base_url = "http://127.0.0.1:7863"
        with patch.object(ww.urllib.request, "urlopen",
                          side_effect=urllib.error.URLError("boom")):
            api._cancel_evaluation("job-42")  # must not raise

    # --- Windows / winforms: dialog runs inline on the UI thread (2-button) -

    def test_windows_no_job_closes_without_dialog(self):
        on_closing, window, api = self._wire(job=None, platform="win32")
        assert on_closing() is True
        window.create_confirmation_dialog.assert_not_called()

    def test_windows_shows_dialog_inline_on_the_calling_thread(self):
        # winforms' create_confirmation_dialog is a direct modal MessageBox with
        # no GUI-thread marshaling; showing it on a worker thread would make it
        # ownerless/non-modal. The winforms closing handler already runs on the
        # UI thread, so it is shown inline and answered synchronously.
        import threading
        caller = threading.get_ident()
        seen = {}
        on_closing, window, api = self._wire(job={"jobId": "x"}, platform="win32")
        window.create_confirmation_dialog.side_effect = (
            lambda *a, **k: seen.__setitem__("tid", threading.get_ident()) or True
        )
        assert on_closing() is True  # OK -> keep -> allow the native close
        assert seen["tid"] == caller  # shown on the UI thread, not a worker
        window.create_confirmation_dialog.assert_called_once()
        window.destroy.assert_not_called()  # inline path lets the native close proceed
        api._cancel_evaluation.assert_not_called()  # cancel-scan is macOS-only

    def test_windows_cancel_blocks_close(self):
        on_closing, window, api = self._wire(job={"jobId": "x"}, platform="win32")
        window.create_confirmation_dialog.return_value = False
        assert on_closing() is False

    def test_windows_dialog_failure_does_not_trap_the_user(self):
        on_closing, window, api = self._wire(job={"jobId": "x"}, platform="win32")
        window.create_confirmation_dialog.side_effect = RuntimeError("no GUI")
        assert on_closing() is True


@_MACOS_ONLY
class TestMacConfirmClose:
    """Exercise the real _macos_confirm_close AppKit body with AppHelper.callAfter
    run inline and NSAlert mocked, so button order, choice mapping, the
    Stay-is-default fix, and semaphore-release-on-error are verified without a
    real modal (mirrors TestMacTrafficLights)."""

    def _run(self, run_modal_result=None, run_modal_error=None):
        import AppKit
        from PyObjCTools import AppHelper
        added = []
        keyeq = {}

        def _add(title):
            added.append(title)
            btn = MagicMock()
            btn.setKeyEquivalent_.side_effect = lambda k, t=title: keyeq.__setitem__(t, k)
            return btn

        alert = MagicMock()
        alert.addButtonWithTitle_.side_effect = _add
        if run_modal_error is not None:
            alert.runModal.side_effect = run_modal_error
        else:
            alert.runModal.return_value = run_modal_result
        with patch.object(AppKit, "NSAlert") as NSAlert, \
             patch.object(AppKit, "NSApplication"), \
             patch.object(AppKit, "NSRunningApplication"), \
             patch.object(AppHelper, "callAfter", side_effect=lambda f, *a: f()), \
             patch.object(ww.sys, "platform", "darwin"):
            NSAlert.alloc.return_value.init.return_value = alert
            choice = ww._macos_confirm_close(MagicMock())
        return choice, added, keyeq

    def test_buttons_added_in_order_keep_cancel_stay(self):
        import AppKit
        _, added, _ = self._run(run_modal_result=AppKit.NSAlertFirstButtonReturn)
        assert added == ["Quit, keep scanning", "Cancel scan and quit", "Stay"]

    def test_choice_mapping_matches_button_order(self):
        import AppKit
        assert self._run(run_modal_result=AppKit.NSAlertFirstButtonReturn)[0] == "keep"
        assert self._run(run_modal_result=AppKit.NSAlertSecondButtonReturn)[0] == "cancel"
        assert self._run(run_modal_result=AppKit.NSAlertThirdButtonReturn)[0] == "stay"

    def test_stay_is_the_default_enter_button(self):
        import AppKit
        _, _, keyeq = self._run(run_modal_result=AppKit.NSAlertThirdButtonReturn)
        assert keyeq.get("Stay") == "\r"                 # Enter -> the safe option
        assert keyeq.get("Quit, keep scanning") == ""      # a reflexive Enter no longer quits

    def test_runmodal_error_returns_keep_and_does_not_hang(self):
        # The semaphore must be released in the finally even if runModal raises,
        # or the worker would hang (the deadlock class this file already hit).
        choice, _, _ = self._run(run_modal_error=RuntimeError("boom"))
        assert choice == "keep"


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


class TestMacFullscreenChrome:
    def test_fullscreen_drops_toolbar(self):
        # macOS draws the unified toolbar as an empty gray bar at the top in
        # fullscreen — drop it (the lights it centers are hidden there anyway).
        window = MagicMock()
        nswindow = window.native
        with patch.object(ww.threading, "Thread", _SyncThread), \
             patch.object(ww, "_apply_unified_toolbar") as restore:
            ww._apply_macos_fullscreen_chrome(window, True)
        nswindow.setToolbar_.assert_called_once_with(None)
        restore.assert_not_called()
        assert window.evaluate_js.call_args.args[0].endswith("true)")

    def test_windowed_restores_toolbar(self):
        window = MagicMock()
        nswindow = window.native
        with patch.object(ww.threading, "Thread", _SyncThread), \
             patch.object(ww, "_apply_unified_toolbar") as restore:
            ww._apply_macos_fullscreen_chrome(window, False)
        restore.assert_called_once_with(nswindow)
        nswindow.setToolbar_.assert_not_called()
        assert window.evaluate_js.call_args.args[0].endswith("false)")

    def test_load_sync_does_not_re_add_toolbar(self):
        # The initial install owns the windowed toolbar; the load-time sync
        # must not add a second one (restore_toolbar=False).
        window = MagicMock()
        nswindow = window.native
        with patch.object(ww.threading, "Thread", _SyncThread), \
             patch.object(ww, "_apply_unified_toolbar") as restore:
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
