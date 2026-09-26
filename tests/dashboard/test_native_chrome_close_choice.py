"""Close-confirm dialog choice: platform dispatch, NSAlert mapping and _cancel_evaluation."""
import logging
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard import _webview_window_close as wwc
from tests.dashboard._native_chrome_helpers import _MACOS_ONLY


class TestOnClosingChoice:
    """The choice seam behind make_on_closing (see test_native_chrome_close.py)."""

    # --- ask_close_choice: platform dispatch + 2-button mapping ------------

    def test_ask_close_choice_macos_dispatches_to_native_alert(self):
        window = MagicMock()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(wwc, "macos_confirm_close", return_value="cancel") as mac:
            assert ww.ask_close_choice(window) == "cancel"
        mac.assert_called_once_with(window)

    def test_ask_close_choice_non_macos_ok_is_keep(self):
        window = MagicMock()
        window.create_confirmation_dialog.return_value = True
        with patch.object(ww.sys, "platform", "linux"):
            assert ww.ask_close_choice(window) == "keep"

    def test_ask_close_choice_non_macos_cancel_is_stay(self):
        window = MagicMock()
        window.create_confirmation_dialog.return_value = False
        with patch.object(ww.sys, "platform", "linux"):
            assert ww.ask_close_choice(window) == "stay"

    def test_ask_close_choice_non_macos_dialog_error_is_keep(self):
        window = MagicMock()
        window.create_confirmation_dialog.side_effect = RuntimeError("no GUI")
        with patch.object(ww.sys, "platform", "linux"):
            assert ww.ask_close_choice(window) == "keep"

    def test_ask_close_choice_non_macos_dialog_error_logs_the_traceback(self, caplog):
        window = MagicMock()
        window.create_confirmation_dialog.side_effect = RuntimeError("no GUI")
        with patch.object(ww.sys, "platform", "linux"), \
             caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_close"):
            assert ww.ask_close_choice(window) == "keep"
        matching = [r for r in caplog.records if "close dialog failed" in r.getMessage()]
        assert matching, [r.getMessage() for r in caplog.records]
        assert any(r.exc_info for r in matching)

    def test_ask_close_choice_non_macos_out_of_scope_error_propagates(self):
        """R-FT-7 — an error outside (WebViewException, OSError, RuntimeError)
        must now propagate instead of being swallowed as 'keep'."""
        window = MagicMock()
        window.create_confirmation_dialog.side_effect = ValueError("bad args")
        with patch.object(ww.sys, "platform", "linux"):
            with pytest.raises(ValueError, match="bad args"):
                ww.ask_close_choice(window)

    # --- _ask_close_choice_isolated: the fault-isolation boundary above -----
    # ask_close_choice. prompt_close_choice_and_finish runs as a bare
    # threading.Thread target with no run_isolated above it, so an
    # out-of-tuple ask_close_choice error (anything past its own narrowed
    # (WebViewException, OSError, RuntimeError)) must be caught HERE instead.

    def test_isolated_out_of_scope_error_yields_keep(self):
        window = MagicMock()
        with patch.object(wwc, "ask_close_choice", side_effect=ValueError("boom")):
            assert wwc._ask_close_choice_isolated(window) == "keep"

    def test_isolated_out_of_scope_error_logs_the_traceback(self, caplog):
        window = MagicMock()
        with patch.object(wwc, "ask_close_choice", side_effect=ValueError("boom")), \
             caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_close"):
            assert wwc._ask_close_choice_isolated(window) == "keep"
        matching = [r for r in caplog.records if "close dialog failed" in r.getMessage()]
        assert matching, [r.getMessage() for r in caplog.records]
        assert any(r.exc_info for r in matching)
        assert "Traceback (most recent call last)" in caplog.text
        assert "ValueError: boom" in caplog.text

    def test_isolated_returns_the_real_choice_when_no_error(self):
        window = MagicMock()
        with patch.object(wwc, "ask_close_choice", return_value="cancel"):
            assert wwc._ask_close_choice_isolated(window) == "cancel"

    # --- NSAlert return -> choice mapping (pure) ----------------------------

    def test_alert_return_to_choice_mapping(self):
        assert ww.alert_return_to_choice(1000, 1000, 1001) == "keep"
        assert ww.alert_return_to_choice(1001, 1000, 1001) == "cancel"
        assert ww.alert_return_to_choice(1002, 1000, 1001) == "stay"

    def test_macos_confirm_close_off_macos_is_safe_default(self):
        # macOS-only path: off darwin it must degrade without touching AppKit.
        with patch.object(ww.sys, "platform", "linux"):
            assert ww.macos_confirm_close(MagicMock()) == "keep"

    # --- _cancel_evaluation -------------------------------------------------

    def test_cancel_evaluation_issues_delete_with_origin(self):
        api = ww.WindowApi()
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
        api = ww.WindowApi()
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
        api = ww.WindowApi()
        api._base_url = "http://127.0.0.1:7863"
        with patch("urllib.request.urlopen",
                    side_effect=urllib.error.URLError("boom")):
            api._cancel_evaluation("job-42")  # must not raise

    def test_cancel_evaluation_swallows_truncated_response(self):
        # http.client.HTTPException (e.g. IncompleteRead) is not an OSError.
        import http.client
        api = ww.WindowApi()
        api._base_url = "http://127.0.0.1:7863"
        with patch("urllib.request.urlopen",
                    side_effect=http.client.IncompleteRead(b"partial")):
            api._cancel_evaluation("job-42")  # must not raise


class TestSaveViaDialogLogsFailure:
    """save_via_dialog (_webview_window_native_ops, re-exported via ww): already
    narrow to OSError; now also logs a warning with the traceback instead of
    silently returning False. Exercised via the module alias already imported
    above rather than a new named import, so it doesn't add a private-import
    baseline entry."""

    def _window(self, save_path: str) -> MagicMock:
        window = MagicMock()
        window.create_file_dialog.return_value = save_path
        return window

    def test_write_failure_logs_a_warning_with_the_path(self, tmp_path, caplog):
        bad_path = str(tmp_path / "does-not-exist" / "output.txt")
        window = self._window(bad_path)
        with caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_native_ops"):
            result = ww.save_via_dialog(window, "content", "output.txt")
        assert result is False
        matching = [r for r in caplog.records if bad_path in r.getMessage()]
        assert matching, [r.getMessage() for r in caplog.records]
        assert any(r.exc_info for r in matching)

    def test_write_success_returns_true_without_logging(self, tmp_path, caplog):
        good_path = str(tmp_path / "output.txt")
        window = self._window(good_path)
        with caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_native_ops"):
            result = ww.save_via_dialog(window, "content", "output.txt")
        assert result is True
        assert not caplog.records


@_MACOS_ONLY
class TestMacConfirmClose:
    """Exercise the real macos_confirm_close AppKit body with AppHelper.callAfter
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
            choice = ww.macos_confirm_close(MagicMock())
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

    def test_runmodal_error_logs_the_traceback(self, caplog):
        with caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_close"):
            choice, _, _ = self._run(run_modal_error=RuntimeError("boom"))
        assert choice == "keep"
        matching = [r for r in caplog.records if "failed" in r.getMessage()]
        assert matching, [r.getMessage() for r in caplog.records]
        assert any(r.exc_info for r in matching)

    def test_build_macos_alert_stores_the_choice_before_releasing_done(self):
        """The worker thread in macos_confirm_close wakes on done.release()
        and immediately reads result["choice"]. If the release ever fires
        before the choice is written, that worker can read the stale
        default instead of the user's answer -- this proves the write
        happens first, by recording the choice at the moment release()
        itself is called (a real threading.Semaphore can't observe this: by
        the time a real worker wakes up, the write has always already
        happened in memory, race or not)."""
        import AppKit

        alert = MagicMock()
        alert.addButtonWithTitle_.side_effect = lambda title: MagicMock()
        alert.runModal.return_value = AppKit.NSAlertSecondButtonReturn  # -> "cancel"

        result = {"choice": "keep"}

        class _OrderRecordingSemaphore:
            def __init__(self) -> None:
                self.choice_at_release = "not released yet"

            def release(self) -> None:
                self.choice_at_release = result["choice"]

        fake_done = _OrderRecordingSemaphore()

        with patch.object(AppKit, "NSAlert") as NSAlert, \
             patch.object(AppKit, "NSApplication"), \
             patch.object(AppKit, "NSRunningApplication"):
            NSAlert.alloc.return_value.init.return_value = alert
            wwc._build_macos_alert(result, fake_done)

        assert result["choice"] == "cancel"
        assert fake_done.choice_at_release == "cancel"
