"""Close-confirmation dialog orchestration, backend dispatch, and the
close-choice seam itself.

_ask_close_choice and _prompt_close_choice_and_finish live here rather than
in the facade (_webview_window.py): _ask_close_choice is patch-tested
against this module's own namespace (`patch.object(wwc, "_ask_close_choice")`
in tests/dashboard/test_native_chrome.py, where ``wwc`` is this module) and
_prompt_close_choice_and_finish bare-calls it from here, so both need to
live together. The facade re-exports both names so
``ww._ask_close_choice(window)`` direct calls keep working, but a patch on
the facade's re-export would not intercept the bare call made from this
module — tests patch this module directly.
"""
from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.dashboard._webview_window import _WindowApi

_logger = logging.getLogger(__name__)

_CLOSE_CONFIRM_TITLE = "Quit quodeq?"
# 2-button backends (OK = quit and keep scanning, Cancel = stay open).
_CLOSE_CONFIRM_BODY = (
    "A scan is running. Quit anyway? The scan keeps running in the background."
)
# macOS 3-button alert informative text.
_CLOSE_CONFIRM_BODY_3WAY = (
    "A scan is running. It keeps running in the background unless you cancel it."
)


def _alert_return_to_choice(ret: int, first: int, second: int) -> str:
    """Map an NSAlert ``runModal()`` return code to a close choice.

    first button -> 'keep' (quit, scan continues), second -> 'cancel' (stop the
    scan, then quit), anything else (third/Stay/Escape) -> 'stay'.
    """
    if ret == first:
        return "keep"
    if ret == second:
        return "cancel"
    return "stay"


def _macos_confirm_close(window: object) -> str:
    """Show the macOS 3-button close dialog and return 'keep', 'cancel', or 'stay'.

    Runs the modal on the GUI/main thread (``NSAlert.runModal`` requires it) via
    ``AppHelper.callAfter``, blocking the *calling* worker thread on a semaphore
    — the same mechanism pywebview's own dialogs use, so this must be called OFF
    the GUI thread. Falls back to 'keep' if AppKit is unavailable or the alert
    fails, so the user is never trapped. No-op ('keep') off macOS.

    The alert is app-modal (not sheeted on the window), so *window* is accepted
    only for call-site symmetry with the 2-button branch and is unused here.
    """
    if sys.platform != "darwin":
        return "keep"
    try:
        import AppKit  # noqa: PLC0415, F401 — import-availability guard
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return "keep"
    result = {"choice": "keep"}
    done = threading.Semaphore(0)
    AppHelper.callAfter(lambda: _show_macos_close_alert(result, done))
    done.acquire()
    return result["choice"]


def _show_macos_close_alert(result: dict, done: threading.Semaphore) -> None:
    """Build and run the 3-button NSAlert on the GUI thread; store the choice
    in *result* and release *done* either way. See _macos_confirm_close.
    """
    try:
        import AppKit  # noqa: PLC0415
        AppKit.NSApplication.sharedApplication()
        AppKit.NSRunningApplication.currentApplication().activateWithOptions_(
            AppKit.NSApplicationActivateIgnoringOtherApps,
        )
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(_CLOSE_CONFIRM_TITLE)
        alert.setInformativeText_(_CLOSE_CONFIRM_BODY_3WAY)
        alert.setAlertStyle_(AppKit.NSWarningAlertStyle)
        quit_btn = alert.addButtonWithTitle_("Quit, keep scanning")
        alert.addButtonWithTitle_("Cancel scan and quit")
        stay = alert.addButtonWithTitle_("Stay")
        # Make "Stay" the default so a reflexive Enter during a scan does not
        # quit; the two actions need a deliberate click. Add order (not which
        # button is default) still fixes the return codes mapped below.
        quit_btn.setKeyEquivalent_("")
        stay.setKeyEquivalent_("\r")
        result["choice"] = _alert_return_to_choice(
            alert.runModal(),
            AppKit.NSAlertFirstButtonReturn,
            AppKit.NSAlertSecondButtonReturn,
        )
    except Exception:
        result["choice"] = "keep"
    finally:
        done.release()


def _ask_close_choice(window: object) -> str:
    """Ask the user how to close while a scan runs; return 'keep', 'cancel', or 'stay'.

    macOS gets a 3-button native alert (keep scanning / cancel scan / stay);
    other backends get pywebview's 2-button dialog (OK = keep scanning, Cancel =
    stay). If the dialog can't render, return 'keep' so the user is never
    trapped in an un-closeable window.

    Patch-tested against this module's own namespace
    (``patch.object(wwc, "_ask_close_choice")`` in
    tests/dashboard/test_native_chrome.py) and bare-calls _macos_confirm_close,
    which is patch-tested the same way — both live here so a patch on either
    is visible to the other.
    """
    if sys.platform == "darwin":
        return _macos_confirm_close(window)
    try:
        ok = bool(window.create_confirmation_dialog(
            _CLOSE_CONFIRM_TITLE, _CLOSE_CONFIRM_BODY,
        ))
    except Exception:
        return "keep"
    return "keep" if ok else "stay"


def _prompt_close_choice_and_finish(
    api: "_WindowApi", window: object, state: dict, job_id: str | None,
) -> None:
    """Worker body for the macOS/GTK/Qt close path: ask the close choice, act
    on it, and (unless staying) commit the close. Runs OFF the GUI thread —
    see _make_on_closing_async for why answering inline would self-deadlock.

    Lives here because it bare-calls the patch-tested _ask_close_choice.
    """
    try:
        choice = _ask_close_choice(window)  # 'keep' | 'cancel' | 'stay'
    except Exception:
        choice = "keep"  # never trap the user on an unexpected dialog error
    if choice == "stay":
        state["prompting"] = False  # re-promptable: a later close asks again
        return
    if choice == "cancel":
        api._cancel_evaluation(job_id)
    # Set `confirmed` BEFORE destroy(): on GTK/Qt/winforms window.destroy()
    # re-fires the closing event, and the guard in _on_closing is what lets
    # that re-issued close through instead of looping into another prompt.
    # `prompting` is deliberately left set through the cancel call above so a
    # second close during that window can't pop a duplicate dialog.
    state["confirmed"] = True
    try:
        window.destroy()  # type: ignore[union-attr]
    except Exception:
        _logger.debug("window.destroy after close-confirm failed", exc_info=True)


def _spawn_close_prompt_worker(
    api: "_WindowApi", window: object, state: dict, job_id: str | None,
) -> threading.Thread:
    """Start the close-confirm prompt on a daemon worker thread and return it."""
    worker = threading.Thread(
        target=_prompt_close_choice_and_finish, args=(api, window, state, job_id), daemon=True,
    )
    worker.start()
    return worker


def _make_on_closing_inline(api: "_WindowApi", window: object) -> "Callable[[], bool]":
    """Windows path: the closing handler runs on the UI thread and the dialog is
    a direct modal MessageBox, so show it inline and answer synchronously.

    Windows shows the 2-button dialog (OK = keep scanning, Cancel = stay); the
    cancel-the-scan option is macOS-only for now. Answers with the dialog
    directly rather than via ``_ask_close_choice`` so it does not re-dispatch on
    ``sys.platform`` (this handler is already the win32-only branch).
    """
    def _on_closing() -> bool:
        try:
            job = api._get_running_evaluation()
        except Exception:
            job = None
        if not job:
            return True
        try:
            return bool(window.create_confirmation_dialog(
                _CLOSE_CONFIRM_TITLE, _CLOSE_CONFIRM_BODY,
            ))
        except Exception:
            # If the native dialog can't render, don't trap the user.
            return True
    _on_closing._worker = None  # type: ignore[attr-defined]  # parity with the async path
    return _on_closing


def _make_on_closing_async(api: "_WindowApi", window: object) -> "Callable[[], bool]":
    """macOS / GTK / Qt path: run the (GUI-thread-marshaling, caller-blocking)
    dialog on a worker thread so it can't self-deadlock the closing handler.

    ``state`` is shared between the GUI thread (``_on_closing``) and the worker
    (``_prompt_close_choice_and_finish``, above). Dict-item writes are
    atomic under the GIL; the running job id is passed to the worker as an
    argument (not shared) so a re-entrant close can't make it cancel a
    different job. ``prompting`` stays set until the worker either resolves to
    'stay' (which clears it, allowing a later re-prompt) or commits to closing
    (``confirmed``), so exactly one prompt is ever in flight — even across the
    possibly-slow cancel call.
    """
    state = {"prompting": False, "confirmed": False}

    def _on_closing() -> bool:
        if state["confirmed"]:
            return True  # user already confirmed; let the re-issued close through
        try:
            job = api._get_running_evaluation()
        except Exception:
            job = None
        if not job:
            return True
        if not state["prompting"]:
            state["prompting"] = True
            job_id = job.get("jobId") or job.get("job_id")
            _on_closing._worker = _spawn_close_prompt_worker(  # type: ignore[attr-defined]
                api, window, state, job_id,
            )
        return False  # veto now; the worker re-closes the window if confirmed

    _on_closing._worker = None  # type: ignore[attr-defined]
    return _on_closing


def _make_on_closing(api: "_WindowApi", window: object) -> "Callable[[], bool]":
    """Native close handler: confirm via a native dialog if a scan is running.

    The scan is a separate process, so quitting just closes the window and the
    scan keeps running — unless the user picks "Cancel scan and quit" (macOS),
    which stops it first.

    pywebview's ``closing`` event is a *locking* event: its handler runs
    synchronously on the GUI thread (on macOS, inside ``windowShouldClose:``).
    How the confirmation dialog can be shown from there depends on the backend:

    * macOS / GTK / Qt — the native dialog marshals back onto the GUI thread and
      then blocks its caller on a semaphore, so answering inline from the
      GUI-thread closing handler self-deadlocks. So we veto the close, show the
      dialog on a worker thread, and re-issue the close via ``window.destroy``
      once the user confirms (see _make_on_closing_async).

    * Windows — winforms' ``create_confirmation_dialog`` is a *direct* modal
      ``MessageBox.Show`` with no GUI-thread marshaling, so a worker thread would
      make it ownerless/non-modal; it's shown inline instead (see
      _make_on_closing_inline). winforms doesn't self-block, so there is no
      deadlock.
    """
    if sys.platform == "win32":
        return _make_on_closing_inline(api, window)
    return _make_on_closing_async(api, window)
