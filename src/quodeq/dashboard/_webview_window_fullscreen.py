"""macOS native-fullscreen observer: keeps the topbar chrome in sync.

_apply_macos_fullscreen_chrome stays in the facade (_webview_window.py): it
bare-calls the patch-tested ``_apply_unified_toolbar``
(`patch.object(ww, "_apply_unified_toolbar")` in
tests/dashboard/test_native_chrome.py), so it must live where that patch is
visible. Nothing in this module is itself patch-tested — tests call
_install_macos_fullscreen_observer directly, which works from any module —
so the observer registration is free to live here. The import of
_apply_macos_fullscreen_chrome is deferred (inside the function) to avoid a
circular import, since the facade imports _install_macos_fullscreen_observer
from here at module load time.
"""
from __future__ import annotations

import sys

_macos_fullscreen_observer: object | None = None  # keep the ObjC observer alive
_macos_fullscreen_observer_installed = False  # register the notifications once
_macos_fullscreen_handler_class = None  # the ObjC handler class is defined once per process


def _build_fullscreen_handler_class(window: object) -> type:
    """Define (once per process — see _install_macos_fullscreen_observer) the
    ObjC observer class that reflects native fullscreen transitions into the
    chrome via _apply_macos_fullscreen_chrome.
    """
    import AppKit  # noqa: PLC0415
    from quodeq.dashboard._webview_window import _apply_macos_fullscreen_chrome  # noqa: PLC0415

    class _FullScreenHandler(AppKit.NSObject):
        def willEnterFullScreen_(self, note):  # noqa: ARG002, N802 — ObjC selector
            # Drop the toolbar BEFORE the enter animation, not after: the
            # *Did*EnterFullScreen notification only fires once the grow
            # animation completes, so the toolbar would stay attached for
            # the whole animation and flash as a gray bar. *Will*Enter runs
            # first, so the animation has no toolbar to show.
            _apply_macos_fullscreen_chrome(window, True)

        def didExitFullScreen_(self, note):  # noqa: ARG002, N802 — ObjC selector
            # Restore only once fully windowed — re-adding during the exit
            # animation would briefly reattach the toolbar while still
            # fullscreen and flash gray again.
            _apply_macos_fullscreen_chrome(window, False)

    return _FullScreenHandler


def _sync_fullscreen_observer(window: object, nswindow: object) -> None:
    """Register the fullscreen observer once (cached handler class), then
    sync the current fullscreen state into the chrome. Runs on the UI thread
    via AppHelper.callAfter (see _install_macos_fullscreen_observer).
    """
    import AppKit  # noqa: PLC0415
    from Foundation import NSNotificationCenter  # noqa: PLC0415
    from quodeq.dashboard._webview_window import _apply_macos_fullscreen_chrome  # noqa: PLC0415

    global _macos_fullscreen_observer, _macos_fullscreen_observer_installed
    try:
        if not _macos_fullscreen_observer_installed:
            observer = _macos_fullscreen_handler_class.alloc().init()
            center = NSNotificationCenter.defaultCenter()
            center.addObserver_selector_name_object_(
                observer, "willEnterFullScreen:",
                AppKit.NSWindowWillEnterFullScreenNotification, nswindow,
            )
            center.addObserver_selector_name_object_(
                observer, "didExitFullScreen:",
                AppKit.NSWindowDidExitFullScreenNotification, nswindow,
            )
            _macos_fullscreen_observer = observer  # keep it alive
            _macos_fullscreen_observer_installed = True
        is_full = bool(nswindow.styleMask() & AppKit.NSWindowStyleMaskFullScreen)
        # Don't re-add the toolbar windowed — _set_macos_unified_toolbar
        # already installed it; a second one would race/flicker.
        _apply_macos_fullscreen_chrome(window, is_full, restore_toolbar=False)
    except (AttributeError, ValueError, TypeError):
        pass


def _install_macos_fullscreen_observer(window: object) -> None:
    """React to native fullscreen transitions so the chrome stays clean.

    On enter/exit fullscreen, drop/restore the unified toolbar and toggle a
    `macos-fullscreen` class on <html> (see _apply_macos_fullscreen_chrome).

    Uses NSWindow fullscreen notifications because they are the only reliable
    signal: on a notched display a zoomed window and a fullscreen window report
    identical inner/screen heights, so a JS heuristic can't tell them apart.

    Registers the notifications once (_build_fullscreen_handler_class) but
    re-syncs the current state on every call (_sync_fullscreen_observer), so
    reloading the page while fullscreen keeps the chrome correct. No-op off
    macOS or before the native handle exists. Call from the ``loaded`` event.
    """
    global _macos_fullscreen_handler_class
    if sys.platform != "darwin":
        return
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is None:
        return

    # Define the ObjC handler class at most once: redefining an NSObject
    # subclass in the same process raises objc.error (the same trap the About
    # panel hit).
    if _macos_fullscreen_handler_class is None:
        _macos_fullscreen_handler_class = _build_fullscreen_handler_class(window)

    AppHelper.callAfter(lambda: _sync_fullscreen_observer(window, nswindow))
