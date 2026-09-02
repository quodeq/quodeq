"""Native window chrome: titlebar appearance, traffic lights, unified toolbar.

Leaf helpers for _webview_window.py. Callers that are patch-tested (e.g. the
titlebar-theme dispatch in _WindowApi, the fullscreen-chrome sync) stay in the
facade and bare-call these by name; moving THEM here would break
`patch.object(ww, "<name>")` mocks in tests/dashboard/test_native_chrome.py,
which patch the facade module's own namespace.
"""
from __future__ import annotations

import logging
import sys
import threading

_logger = logging.getLogger(__name__)

_macos_toolbar_installed = False  # the unified toolbar (taller titlebar) is added once


def _set_macos_titlebar_appearance(window: object, dark: bool) -> None:
    """Set the macOS native titlebar to dark or light aqua (on the UI thread)."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import (  # noqa: PLC0415
            NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua,
        )
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is None:
        return
    name = NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua

    def _apply() -> None:
        try:
            nswindow.setAppearance_(NSAppearance.appearanceNamed_(name))
        except (AttributeError, ValueError):
            pass

    AppHelper.callAfter(_apply)


def _show_macos_traffic_lights(window: object) -> None:
    """Re-show the native traffic lights on the frameless macOS window.

    pywebview hides the standard window buttons for frameless windows, but
    frameless is what enables NSFullSizeContentView (the app's topbar running
    under the titlebar). Un-hiding them gives the unified look — the buttons
    keep their native top-left position (the CSS lays the compact macOS topbar
    out to line up with them), so nothing is repositioned and there is nothing
    to re-apply on resize. Runs on the UI thread; no-op before the native
    handle exists.
    """
    if sys.platform != "darwin":
        return
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is None:
        return

    def _apply() -> None:
        # NSWindowCloseButton=0, NSWindowMiniaturizeButton=1, NSWindowZoomButton=2
        for button_id in (0, 1, 2):
            try:
                btn = nswindow.standardWindowButton_(button_id)
                if btn is not None:
                    btn.setHidden_(False)
            except (AttributeError, ValueError):
                pass

    AppHelper.callAfter(_apply)


def _apply_unified_toolbar(nswindow: object) -> None:
    """Attach an empty unified-compact NSToolbar so the native titlebar grows
    just enough to drop the traffic lights to ~20px from the top — vertically
    centered in the 40px in-app topbar (--app-header-h). macOS keeps the lights
    centered across resize, so nothing is repositioned by hand (no jump).

    Must run on the UI thread; AppKit failures are the caller's to swallow.
    """
    import AppKit  # noqa: PLC0415
    toolbar = AppKit.NSToolbar.alloc().initWithIdentifier_("quodeq-titlebar")
    toolbar.setShowsBaselineSeparator_(False)
    nswindow.setToolbar_(toolbar)
    nswindow.setToolbarStyle_(4)  # NSWindowToolbarStyleUnifiedCompact
    # Remove the 1px separator line under the toolbar (most visible in
    # fullscreen). NSTitlebarSeparatorStyleNone = 1 (macOS 11+).
    nswindow.setTitlebarSeparatorStyle_(1)


def _set_macos_unified_toolbar(window: object) -> None:
    """Install the unified-compact toolbar (see _apply_unified_toolbar) on the
    frameless macOS window. Installed once; no-op off macOS or before the
    native handle exists.
    """
    global _macos_toolbar_installed
    if _macos_toolbar_installed or sys.platform != "darwin":
        return
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is None:
        return
    _macos_toolbar_installed = True

    def _apply() -> None:
        try:
            _apply_unified_toolbar(nswindow)
        except (AttributeError, ValueError, TypeError):
            pass

    AppHelper.callAfter(_apply)


def _set_macos_fullscreen_class(window: object, is_full: bool) -> None:
    """Toggle the `macos-fullscreen` class on <html> from off the main thread.

    pywebview's evaluate_js blocks waiting on the JS engine, which deadlocks
    when called on the AppKit main thread (where notifications fire), so run it
    on a short-lived worker thread.
    """
    flag = "true" if is_full else "false"
    js = f"document.documentElement.classList.toggle('macos-fullscreen', {flag})"

    def _run() -> None:
        try:
            window.evaluate_js(js)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 — window may be tearing down
            _logger.debug("fullscreen class toggle failed", exc_info=True)

    threading.Thread(target=_run, daemon=True).start()


def _set_windows_titlebar(dark: bool, window_title: str = "quodeq") -> None:
    """Set the native Windows titlebar dark/light via DWM (attr 20, fallback 19)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if not hwnd:
            return
        value = ctypes.c_int(1 if dark else 0)
        size = ctypes.sizeof(value)
        for attr in (20, 19):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), wintypes.DWORD(attr),
                ctypes.byref(value), wintypes.DWORD(size),
            )
            if res == 0:
                return
    except (AttributeError, OSError):
        pass
