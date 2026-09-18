"""Native-chrome close handler: off-thread prompt on macOS/GTK/Qt, inline dialog on Windows."""
from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard import _webview_window_close as wwc
from tests._timeouts import budget


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
            worker.join(timeout=budget(2))
            # A hung worker is the exact failure class this fix targets — surface
            # it as itself, not as a downstream mock-call-count mismatch.
            assert not worker.is_alive(), "close-confirm worker did not finish (possible re-deadlock)"

    # --- async (macOS / GTK / Qt): dialog runs off the GUI thread -----------

    def test_no_job_closes_without_prompt(self):
        on_closing, window, api = self._wire(job=None)
        with patch.object(wwc, "_ask_close_choice") as choose:
            assert on_closing() is True
        choose.assert_not_called()

    def test_running_job_vetoes_the_close_and_prompts_async(self):
        # A running scan must NOT be answered synchronously: the native dialog
        # marshals onto the GUI thread and blocks its caller, so answering from
        # the closing handler (which runs ON the GUI thread) self-deadlocks. The
        # handler vetoes this close and shows the dialog on a worker thread.
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(wwc, "_ask_close_choice", return_value="stay") as choose:
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

        with patch.object(wwc, "_ask_close_choice", side_effect=_choose):
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

        with patch.object(wwc, "_ask_close_choice", side_effect=_choose):
            result = []
            caller = threading.Thread(target=lambda: result.append(on_closing()))
            caller.start()
            caller.join(timeout=budget(2))
            try:
                assert not caller.is_alive(), "_on_closing blocked on the dialog — re-deadlock regression"
                assert result == [False]
            finally:
                release.set()
                self._join(on_closing)

    def test_keep_scanning_closes_window_without_cancelling(self):
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(wwc, "_ask_close_choice", return_value="keep"):
            on_closing()
            self._join(on_closing)
        window.destroy.assert_called_once()
        api._cancel_evaluation.assert_not_called()
        # The re-issued close (from destroy) is allowed straight through.
        assert on_closing() is True

    def test_cancel_scan_and_quit_cancels_then_closes(self):
        on_closing, window, api = self._wire(job={"jobId": "job-42"})
        with patch.object(wwc, "_ask_close_choice", return_value="cancel"):
            on_closing()
            self._join(on_closing)
        api._cancel_evaluation.assert_called_once_with("job-42")
        window.destroy.assert_called_once()
        assert on_closing() is True

    def test_stay_keeps_window_open_and_can_reprompt(self):
        on_closing, window, api = self._wire(job={"jobId": "x"})
        with patch.object(wwc, "_ask_close_choice", return_value="stay") as choose:
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

        with patch.object(wwc, "_ask_close_choice", side_effect=_choose):
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
        with patch.object(wwc, "_ask_close_choice", return_value="cancel") as choose:
            assert on_closing() is False
            first_worker = on_closing._worker
            assert cancel_started.wait(budget(2))  # worker is now inside the cancel call
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
        with patch.object(wwc, "_ask_close_choice", side_effect=RuntimeError("no GUI")):
            assert on_closing() is False
            self._join(on_closing)
        window.destroy.assert_called_once()
        api._cancel_evaluation.assert_not_called()

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
