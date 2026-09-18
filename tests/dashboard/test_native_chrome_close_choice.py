"""Close-confirm dialog choice: platform dispatch, NSAlert mapping and _cancel_evaluation."""
from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard import _webview_window_close as wwc
from tests.dashboard._native_chrome_helpers import _MACOS_ONLY


class TestOnClosingChoice:
    """The choice seam behind _make_on_closing (see test_native_chrome_close.py)."""

    # --- _ask_close_choice: platform dispatch + 2-button mapping ------------

    def test_ask_close_choice_macos_dispatches_to_native_alert(self):
        window = MagicMock()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(wwc, "_macos_confirm_close", return_value="cancel") as mac:
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

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            api._cancel_evaluation("job-42")
        assert captured["url"] == "http://127.0.0.1:7863/api/evaluations/job-42"
        assert captured["method"] == "DELETE"
        assert captured["origin"] == "http://127.0.0.1:7863"

    def test_cancel_evaluation_noop_without_job_or_base_url(self):
        api = ww._WindowApi()
        with patch("urllib.request.urlopen") as uo:
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
        with patch("urllib.request.urlopen",
                    side_effect=urllib.error.URLError("boom")):
            api._cancel_evaluation("job-42")  # must not raise


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
