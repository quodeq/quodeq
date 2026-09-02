"""Window lifecycle hooks: what runs once pywebview's ``loaded`` event fires.

Nothing here is patch-tested by name (tests exercise the individual chrome
setters through _WindowApi.set_titlebar_theme / _ask_close_choice's own call
sites in the facade, not through this orchestration layer), so it is free to
live outside the facade. main() (in _webview_window.py) imports
_make_on_loaded from here.
"""
from __future__ import annotations

import sys
from collections.abc import Callable

from quodeq.dashboard._webview_window_about import _set_macos_app_identity
from quodeq.dashboard._webview_window_chrome import (
    _logger,
    _set_macos_titlebar_appearance,
    _set_macos_unified_toolbar,
    _set_windows_titlebar,
    _show_macos_traffic_lights,
)
from quodeq.dashboard._webview_window_fullscreen import _install_macos_fullscreen_observer
from quodeq.dashboard._webview_window_help_menu import _install_macos_help_menu


def _run_macos_loaded_hooks(window: object) -> None:
    """macOS-only chrome setup once the window has been shown.

    Show the native traffic lights FIRST: they are the only window controls
    on the frameless macOS window, so they must not be skipped if a later,
    best-effort step raises.
    """
    _show_macos_traffic_lights(window)
    _set_macos_unified_toolbar(window)
    _set_macos_titlebar_appearance(window, True)
    # Reflect fullscreen state in a CSS class so the topbar border and the
    # traffic-light reservation drop when macOS hides the lights.
    _install_macos_fullscreen_observer(window)
    # Re-apply the dock icon + bundle name now that pywebview's NSApplication
    # is live (the early call in main() targets the pre-pywebview NSApp).
    # Best-effort — never block the controls.
    try:
        _set_macos_app_identity()
    except Exception:
        _logger.debug("macOS app-identity setup failed", exc_info=True)
    # Native Help menu → dashboard help tab. Best-effort like the identity
    # setup: a failure must never block window chrome.
    try:
        _install_macos_help_menu(window)
    except Exception:
        _logger.debug("macOS Help menu setup failed", exc_info=True)


def _make_on_loaded(window: object) -> "Callable[[], None]":
    """Return the ``loaded`` handler bound to *window* (mirrors _make_on_reload)."""
    def _on_loaded() -> None:
        window.show()
        if sys.platform == "darwin":
            _run_macos_loaded_hooks(window)
        elif sys.platform == "win32":
            _set_windows_titlebar(True)

    return _on_loaded
