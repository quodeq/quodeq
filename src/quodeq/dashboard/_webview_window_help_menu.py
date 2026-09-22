"""Native Help menu: macOS Apple-menu item + the Windows/Linux menu bar.

Leaf module for _webview_window.py. _NAVIGATE_HELP_JS and _non_macos_menu are
imported directly by tests/dashboard/test_webview_menu.py and re-exported by
the facade for that reason; nothing here is patch-tested via
`patch.object(ww, ...)`, so no caller/callee co-location constraint applies.
"""
from __future__ import annotations

import sys
import threading

from quodeq.dashboard._webview_window_about import _diag
from quodeq.dashboard._webview_window_chrome import _logger

_help_target: object | None = None  # keep the Help-menu handler alive (menu item holds a weak ref)
_help_menu_installed = False  # the _HelpHandler ObjC class may only be defined once

# Payload both native shells dispatch to open the help tab; routed by the
# React useNativeNavBridge hook (detail must be a KNOWN_TABS entry).
_NAVIGATE_HELP_JS = "window.dispatchEvent(new CustomEvent('quodeq:navigate', { detail: 'help' }))"


def _build_help_handler(window: object) -> object:
    """Build the ObjC handler whose openHelp_ dispatches the navigate event.

    Split out of _install_macos_help_menu so neither half exceeds the
    function-size cap.
    """
    from AppKit import NSObject  # noqa: PLC0415

    class _HelpHandler(NSObject):
        def openHelp_(self, sender):  # noqa: ARG002 — ObjC selector signature
            # Menu actions fire on the AppKit main thread, where evaluate_js
            # deadlocks (it blocks on the JS engine) — hop to a worker thread.
            def _run() -> None:
                try:
                    window.evaluate_js(_NAVIGATE_HELP_JS)  # type: ignore[union-attr]
                except Exception:  # noqa: BLE001 — window may be tearing down
                    _logger.debug("help-menu navigation failed", exc_info=True)
            threading.Thread(target=_run, daemon=True).start()

    return _HelpHandler.alloc().init()


def _build_help_menu(app: object, main_menu: object, target: object) -> None:
    """Append the Help ▸ "quodeq Help" menu and register it as NSApp's help
    menu (macOS then appends its native search field to it).
    """
    from AppKit import NSMenu, NSMenuItem  # noqa: PLC0415

    help_menu = NSMenu.alloc().initWithTitle_("Help")
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "quodeq Help", "openHelp:", "?",
    )
    item.setTarget_(target)
    help_menu.addItem_(item)
    top_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Help", None, "")
    top_item.setSubmenu_(help_menu)
    main_menu.addItem_(top_item)
    app.setHelpMenu_(help_menu)


def _stop_poll_timer(state: dict) -> None:
    if state["timer"]:
        state["timer"].invalidate()


def _schedule_help_menu_poller(target: object) -> None:
    """Poll (via NSTimer) until the main menu exists, then append the Help
    menu and register it with NSApp.setHelpMenu_.
    """
    from AppKit import NSApplication, NSObject  # noqa: PLC0415
    from Foundation import NSTimer  # noqa: PLC0415

    state = {"attempts": 0, "timer": None}
    max_attempts = 25  # ~5 seconds at 200ms

    class _HelpMenuPoller(NSObject):
        def tryInstall_(self, timer):  # noqa: ARG002
            state["attempts"] += 1
            app = NSApplication.sharedApplication()
            main_menu = app.mainMenu()
            if main_menu is None or main_menu.numberOfItems() == 0:
                if state["attempts"] >= max_attempts:
                    print(f"[quodeq-help] gave up after {state['attempts']} attempts — no main menu",
                          file=_diag, flush=True)
                    _stop_poll_timer(state)
                return
            _build_help_menu(app, main_menu, target)
            print(f"[quodeq-help] installed Help menu on attempt {state['attempts']}",
                  file=_diag, flush=True)
            _stop_poll_timer(state)

        def scheduleTimer_(self, arg):  # noqa: ARG002 — ObjC selector signature
            # `loaded` fires on pywebview's own event-dispatch thread, not
            # the AppKit main thread, and a repeating NSTimer only fires if
            # it's scheduled on a run loop that's actually being pumped —
            # the calling thread's run loop otherwise sits idle forever and
            # tryInstall_ never ticks. Hop to the main thread to schedule it
            # (the same hop as openHelp_ above, in the opposite direction).
            try:
                timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.2, self, "tryInstall:", None, True,
                )
                state["timer"] = timer
            except (AttributeError, ValueError) as exc:
                print(f"[quodeq-help] NSTimer schedule failed: {exc}", file=_diag, flush=True)

    poller = _HelpMenuPoller.alloc().init()
    # Retain the poller so it isn't GC'd while the timer holds a weak ref
    state["poller"] = poller
    poller.performSelectorOnMainThread_withObject_waitUntilDone_("scheduleTimer:", None, False)


def _install_macos_help_menu(window: object) -> None:
    """Add a top-level Help menu whose item opens the dashboard help tab.

    pywebview's Cocoa backend builds the main menu lazily during the run
    loop, so (like the About override) poll with an NSTimer until the menu
    bar exists (see _schedule_help_menu_poller), then append a "Help" menu.

    The item can't call into React directly; it dispatches a
    ``quodeq:navigate`` CustomEvent that useNativeNavBridge routes to
    ``navTab('help')``.

    Installs at most once: the ObjC classes can only be defined once per
    process (see _install_about_panel_override).
    """
    global _help_target, _help_menu_installed
    if _help_menu_installed:
        return
    try:
        from AppKit import NSApplication, NSMenu, NSMenuItem, NSObject  # noqa: PLC0415, F401
        from Foundation import NSTimer  # noqa: PLC0415, F401
    except ImportError:
        return
    _help_menu_installed = True
    _help_target = _build_help_handler(window)
    _schedule_help_menu_poller(_help_target)


def _non_macos_menu(window: object) -> "list[object] | None":
    """Build the Windows/Linux menu bar: Help ▸ "quodeq Help".

    Those platforms have no menu bar at all (the macOS one is generated by
    Cocoa and patched via _install_macos_help_menu); passing a pywebview
    menu list to webview.start() creates a native bar there. Returns None
    on macOS — a pywebview menu there would append a duplicate Help menu.
    pywebview's menu API has no keyboard accelerators, so no shortcut.
    """
    if sys.platform == "darwin":
        return None
    try:
        import webview.menu as wm  # noqa: PLC0415
    except ImportError:
        return None

    def _open_help() -> None:
        # Menu callbacks fire on the backend's GUI thread, where evaluate_js
        # can deadlock — hop to a worker thread (same discipline as macOS).
        def _run() -> None:
            try:
                window.evaluate_js(_NAVIGATE_HELP_JS)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001 — window may be tearing down
                _logger.debug("help-menu navigation failed", exc_info=True)
        threading.Thread(target=_run, daemon=True).start()

    return [wm.Menu("Help", [wm.MenuAction("quodeq Help", _open_help)])]
