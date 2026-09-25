"""Native window chrome: titlebar appearance, traffic lights, unified toolbar.

Leaf helpers for _webview_window.py. Callers in the facade (the
titlebar-theme dispatch in WindowApi, the fullscreen-chrome sync) reach
set_macos_titlebar_appearance / set_windows_titlebar / apply_unified_toolbar
through this module (imported there as ``_chrome``) rather than by bare name,
so tests/dashboard/test_native_chrome.py patches this module's own namespace
(`patch.object(chrome, "<name>")`, where ``chrome`` is this module) and the
patch is visible regardless of which module made the call.
"""
from __future__ import annotations

import logging
import sys
import threading
from types import ModuleType

from quodeq.shared.constants import PLATFORM_DARWIN, PLATFORM_WIN32

logger = logging.getLogger(__name__)

_macos_toolbar_installed = False  # the unified toolbar (taller titlebar) is added once
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # DWMWINDOWATTRIBUTE id, Windows 10 20H1 and later
_DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1 = 19  # the undocumented id builds before 20H1 used
_S_OK = 0  # HRESULT success


def native_window(window: object) -> object | None:
    """The pywebview *window*'s native handle (the NSWindow on macOS), or None before it exists."""
    return getattr(window, "native", None) if window is not None else None


def macos_native_window(window: object) -> tuple[object, ModuleType] | None:
    """``(nswindow, AppHelper)`` for *window* on macOS, or None.

    None off macOS, without PyObjC, or before the native handle exists: the
    macOS chrome helpers are then no-ops. ``AppHelper.callAfter`` runs work
    on the UI thread.
    """
    if sys.platform != PLATFORM_DARWIN:
        return None
    try:
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return None
    nswindow = native_window(window)
    if nswindow is None:
        return None
    return nswindow, AppHelper


def set_macos_titlebar_appearance(window: object, dark: bool) -> None:
    """Set the macOS native titlebar to dark or light aqua (on the UI thread)."""
    native = macos_native_window(window)
    if native is None:
        return
    nswindow, AppHelper = native
    try:
        from AppKit import (  # noqa: PLC0415
            NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua,
        )
    except ImportError:
        return
    name = NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua

    def _apply() -> None:
        try:
            nswindow.setAppearance_(NSAppearance.appearanceNamed_(name))
        except (AttributeError, ValueError):
            logger.debug("titlebar appearance toggle failed", exc_info=True)

    AppHelper.callAfter(_apply)


def show_macos_traffic_lights(window: object) -> None:
    """Re-show the native traffic lights on the frameless macOS window.

    pywebview hides the standard window buttons for frameless windows, but
    frameless is what enables NSFullSizeContentView (the app's topbar running
    under the titlebar). Un-hiding them gives the unified look — the buttons
    keep their native top-left position (the CSS lays the compact macOS topbar
    out to line up with them), so nothing is repositioned and there is nothing
    to re-apply on resize. Runs on the UI thread; no-op before the native
    handle exists.
    """
    native = macos_native_window(window)
    if native is None:
        return
    nswindow, AppHelper = native
    try:
        from AppKit import (  # noqa: PLC0415
            NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton,
        )
    except ImportError:
        return

    def _apply() -> None:
        for button_id in (NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton):
            try:
                btn = nswindow.standardWindowButton_(button_id)
                if btn is not None:
                    btn.setHidden_(False)
            except (AttributeError, ValueError):
                logger.debug("traffic light visibility toggle failed", exc_info=True)

    AppHelper.callAfter(_apply)


def apply_unified_toolbar(nswindow: object) -> None:
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
    nswindow.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)
    # Remove the 1px separator line under the toolbar (most visible in
    # fullscreen); macOS 11+.
    nswindow.setTitlebarSeparatorStyle_(AppKit.NSTitlebarSeparatorStyleNone)


def set_macos_unified_toolbar(window: object) -> None:
    """Install the unified-compact toolbar (see apply_unified_toolbar) on the
    frameless macOS window. Installed once; no-op off macOS or before the
    native handle exists.
    """
    global _macos_toolbar_installed
    if _macos_toolbar_installed:
        return
    native = macos_native_window(window)
    if native is None:
        return
    nswindow, AppHelper = native
    _macos_toolbar_installed = True

    def _apply() -> None:
        try:
            apply_unified_toolbar(nswindow)
        except (AttributeError, ValueError, TypeError):
            logger.debug("unified toolbar installation failed", exc_info=True)

    AppHelper.callAfter(_apply)


def set_macos_fullscreen_class(window: object, is_full: bool) -> None:
    """Toggle the `macos-fullscreen` class on <html> from off the main thread.

    pywebview's evaluate_js blocks waiting on the JS engine, which deadlocks
    when called on the AppKit main thread (where notifications fire), so run it
    on a short-lived worker thread.
    """
    flag = "true" if is_full else "false"
    js = f"document.documentElement.classList.toggle('macos-fullscreen', {flag})"
    evaluate_js_in_background(window, js, "fullscreen class toggle failed")


def evaluate_js_in_background(window: object, js: str, failure: str) -> None:
    """Run *js* in *window* on a short-lived worker thread.

    For callers on the AppKit main thread or a GUI backend thread, where
    ``evaluate_js`` deadlocks waiting on the JS engine. A failure (the
    window may be tearing down) is logged at debug level as *failure*.
    """
    def _run() -> None:
        try:
            window.evaluate_js(js)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 — window may be tearing down
            logger.debug(failure, exc_info=True)

    threading.Thread(target=_run, daemon=True).start()


def set_windows_titlebar(dark: bool, window_title: str = "quodeq") -> None:
    """Set the native Windows titlebar dark/light via DWM (attr 20, fallback 19)."""
    if sys.platform != PLATFORM_WIN32:
        return
    try:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if not hwnd:
            return
        value = ctypes.c_int(1 if dark else 0)
        size = ctypes.sizeof(value)
        for attr in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1):
            res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), wintypes.DWORD(attr),
                ctypes.byref(value), wintypes.DWORD(size),
            )
            if res == _S_OK:
                return
    except (AttributeError, OSError):
        logger.debug("Windows titlebar DWM configuration failed", exc_info=True)
