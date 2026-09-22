"""macOS app identity: dock icon, bundle name, and the rich About panel.

The webview's user-agent string lives in ``_webview_user_agent`` and is
re-exported here, where ``_webview_window`` and the drift tests have always
imported it from.

The About-panel install writes its progress to the webview diagnostic log
(``_webview_diag``), which this module re-exports as ``_diag`` for the help
menu that writes to the same file.

Leaf module for _webview_window.py — self-contained AppKit setup with no
patch-tested cross-function co-location requirements (see
tests/dashboard/test_native_chrome.py's TestMacAppIdentityIdempotent, which
only calls _set_macos_app_identity directly). The facade re-exports
_set_macos_app_identity and _icon_path, which it also calls itself.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from quodeq.dashboard._webview_diag import _diag
from quodeq.dashboard._webview_user_agent import (
    _WEBVIEW_TOKEN_UA_PREFIX, _WEBVIEW_UA_MARKER, _quodeq_version,
    _webview_user_agent,
)
from quodeq.shared.logging import log_debug

__all__ = [
    "_icon_path", "_install_about_panel_override", "_set_app_icon",
    "_set_macos_app_identity",
    # Re-exported: _webview_window and the drift tests have always imported
    # these from here.
    "_WEBVIEW_TOKEN_UA_PREFIX", "_WEBVIEW_UA_MARKER", "_diag",
    "_quodeq_version", "_webview_user_agent",
]

_APP_DISPLAY_NAME = "quodeq"


@dataclass
class _MacAppState:
    """The AppKit objects this module must outlive a single call to keep alive."""

    app_icon: object | None = None  # the NSImage, reused across _set calls
    about_target: object | None = None  # the menu item holds only a weak ref
    about_override_installed: bool = False  # _AboutHandler may be defined once


_STATE = _MacAppState()

_QUODEQ_WEBSITE = "https://quodeq.com"
_QUODEQ_REPO = "https://github.com/quodeq/quodeq"


def _icon_path(ext: str) -> str | None:
    """Resolve the quodeq icon path for the given extension (.icns or .ico).

    Icons live in package data (`quodeq/data/icons/`) so they ship in the
    wheel — that's what makes the dock icon work under `pipx install`,
    not just the frozen DMG build.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "quodeq" / "data" / "icons"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent / "data" / "icons"
    if ext == ".icns":
        p = base / "icon.icns"
    elif ext == ".ico":
        p = base / "icon.ico"
    else:
        return None
    return str(p) if p.exists() else None


def _build_about_credits() -> object | None:
    """Build a clickable NSAttributedString with website + repo links."""
    try:
        from AppKit import (  # type: ignore[import-untyped]
            NSAttributedString,
            NSMutableAttributedString,
            NSURL,
        )
        from Foundation import NSRange  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return None
    try:
        body = NSMutableAttributedString.alloc().init()

        def _append(text: str, link: str | None = None) -> None:
            url = NSURL.URLWithString_(link) if link else None
            attrs = {} if url is None else {"NSLink": url}
            fragment = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            body.appendAttributedString_(fragment)
        _append(_QUODEQ_WEBSITE, _QUODEQ_WEBSITE)
        _append("\n")
        _append(_QUODEQ_REPO, _QUODEQ_REPO)
        return body
    except (AttributeError, ValueError):
        return None


def _build_about_handler() -> object:
    """Build (but do not install) the ObjC handler whose showAbout_ shows the
    rich About panel. Split out of _install_about_panel_override so neither
    half exceeds the function-size cap.
    """
    from AppKit import NSApplication, NSObject  # noqa: PLC0415

    import datetime as _dt  # noqa: PLC0415
    version = _quodeq_version()
    copyright_line = f"© {_dt.date.today().year} quodeq"

    class _AboutHandler(NSObject):
        def showAbout_(self, sender):  # noqa: ARG002 — ObjC selector signature
            opts: dict[str, object] = {
                "ApplicationName": _APP_DISPLAY_NAME,
                "ApplicationVersion": version,
                "Version": "",  # hide the "Build" line Apple renders by default
                "Copyright": copyright_line,
            }
            if _STATE.app_icon is not None:
                opts["ApplicationIcon"] = _STATE.app_icon
            credits = _build_about_credits()
            if credits is not None:
                opts["Credits"] = credits
            NSApplication.sharedApplication().orderFrontStandardAboutPanelWithOptions_(opts)

    return _AboutHandler.alloc().init()


def _find_about_items(main_menu: object) -> list:
    """Return Apple-menu items whose title starts with 'About'."""
    items = []
    for mi in range(main_menu.numberOfItems()):
        sub = main_menu.itemAtIndex_(mi).submenu()
        if sub is None:
            continue
        for i in range(sub.numberOfItems()):
            item = sub.itemAtIndex_(i)
            title = str(item.title() or "")
            if title.lower().startswith("about"):
                items.append(item)
    return items


def _stop_poll_timer(state: dict) -> None:
    if state["timer"]:
        state["timer"].invalidate()


def _schedule_about_install_poller(target: object) -> None:
    """Poll (via NSTimer) until the About menu item exists, then retarget it
    at *target*. See _install_about_panel_override for why polling is needed.
    """
    from AppKit import NSApplication, NSObject  # noqa: PLC0415
    from Foundation import NSTimer  # noqa: PLC0415

    state = {"attempts": 0, "timer": None}
    max_attempts = 25  # ~5 seconds at 200ms

    class _InstallPoller(NSObject):
        def tryInstall_(self, timer):  # noqa: ARG002
            state["attempts"] += 1
            main_menu = NSApplication.sharedApplication().mainMenu()
            if main_menu is None or main_menu.numberOfItems() == 0:
                if state["attempts"] >= max_attempts:
                    print(f"[quodeq-about] gave up after {state['attempts']} attempts — no main menu",
                          file=_diag, flush=True)
                    _stop_poll_timer(state)
                return
            about_items = _find_about_items(main_menu)
            if not about_items:
                if state["attempts"] >= max_attempts:
                    print(f"[quodeq-about] gave up — no About item found after {state['attempts']} attempts",
                          file=_diag, flush=True)
                    _stop_poll_timer(state)
                return
            for item in about_items:
                item.setTarget_(target)
                item.setAction_("showAbout:")
            print(f"[quodeq-about] retargeted {len(about_items)} About item(s) on attempt {state['attempts']}",
                  file=_diag, flush=True)
            _stop_poll_timer(state)

    poller = _InstallPoller.alloc().init()
    # Retain the poller so it isn't GC'd while the timer holds a weak ref
    state["poller"] = poller
    try:
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.2, poller, "tryInstall:", None, True,
        )
        state["timer"] = timer
    except (AttributeError, ValueError) as exc:
        print(f"[quodeq-about] NSTimer schedule failed: {exc}", file=_diag, flush=True)


def _install_about_panel_override() -> None:
    """Point the Apple-menu 'About …' at a handler that shows a rich panel.

    The app main menu is built lazily by NSApp during the Cocoa run loop.
    On the first call from the `loaded` event it's typically still nil, so
    schedule a repeating NSTimer that retries until the About item exists
    (or we give up after ~5s) — see _schedule_about_install_poller.

    Installs at most once: the ``_AboutHandler`` ObjC class can only be
    defined once per process, so a second call (e.g. on a repeat ``loaded``
    event) would raise ``objc.error`` and abort the caller.
    """
    if _STATE.about_override_installed:
        return
    try:
        from AppKit import NSApplication, NSObject  # noqa: PLC0415, F401
        from Foundation import NSTimer  # noqa: PLC0415, F401
    except ImportError:
        return
    _STATE.about_override_installed = True
    _STATE.about_target = _build_about_handler()
    _schedule_about_install_poller(_STATE.about_target)


def _set_macos_app_identity() -> None:
    """Set dock icon, menu-bar app name, and About-panel icon on macOS.

    Called both at startup (early) and after pywebview is shown — pywebview
    spins up its own NSApplication when start() runs, which overrides the
    early-set icon. Re-applying from the `loaded` event ensures the icon
    lands on the NSApp instance that actually renders the dock tile.

    The About panel (Apple menu → About quodeq) draws from the bundle info
    dict, not the runtime icon image, so we also write NSApplicationIcon
    into the info dict and register a swizzled action on the menu item.
    """
    try:
        from AppKit import NSApplication, NSBundle, NSImage  # type: ignore[import-untyped]
    except ImportError:
        return
    # Patch the bundle name so the menu bar reads "quodeq" instead of "python3".
    # Runtime mutation of the NSBundle info dict; works as long as NSApp
    # hasn't cached the name (i.e. before webview.start draws the menu bar).
    # Repeat calls are harmless.
    try:
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = _APP_DISPLAY_NAME
            info["CFBundleDisplayName"] = _APP_DISPLAY_NAME
    except (AttributeError, TypeError) as exc:
        log_debug(f"bundle name patch skipped: {exc}")
    path = _icon_path(".icns")
    if not path:
        return
    try:
        icon = NSImage.alloc().initWithContentsOfFile_(path)
    except (AttributeError, ValueError):
        icon = None
    if not icon:
        return
    _STATE.app_icon = icon  # keep a live reference for the About-panel override
    try:
        NSApplication.sharedApplication().setApplicationIconImage_(icon)
    except (AttributeError, ValueError) as exc:
        log_debug(f"dock icon not set: {exc}")
    # Override the default About panel so it shows our icon + name. The
    # standard panel reads from Info.plist and ignores setApplicationIconImage_
    # for non-bundled apps, so we wire a custom action on the first-responder
    # chain using orderFrontStandardAboutPanelWithOptions_.
    _install_about_panel_override()


def _set_app_icon() -> None:
    """Set the application icon (dock on macOS, taskbar on Windows)."""
    if sys.platform == "darwin":
        _set_macos_app_identity()
    elif sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            path = _icon_path(".ico")
            if path:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("quodeq.dashboard")
                # Load icon and set for the process
                icon_flags = 0x00000010 | 0x00000001  # LR_LOADFROMFILE | LR_DEFAULTSIZE
                hicon = ctypes.windll.user32.LoadImageW(0, path, 1, 0, 0, icon_flags)
                if hicon:
                    ctypes.windll.user32.SendMessageW(
                        ctypes.windll.kernel32.GetConsoleWindow(), 0x0080, 0, hicon,
                    )
        except (AttributeError, OSError) as exc:
            log_debug(f"windows taskbar icon not set: {exc}")
