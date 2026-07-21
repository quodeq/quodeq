"""PyWebView window process — launched as a subprocess by _server.py."""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

import webview

from quodeq.dashboard._build_npm import _quodeq_dir
from quodeq.dashboard._instance import InstanceController

_logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
_WINDOW_BG_COLOR = '#0d1117'
# Marker embedded in the webview's User-Agent so the API serves it the
# relaxed CSP (see quodeq.api.security._WEBVIEW_UA_MARKER — must match).
_WEBVIEW_UA_MARKER = "QuodeqDesktop"
_EVAL_CHECK_TIMEOUT_S = 0.5
_DOWNLOAD_TIMEOUT_S = 120


def _is_safe_reload_url(url: str) -> bool:
    """Return True only when *url* points to the local dashboard origin.

    Rejects anything that is not http/https on 127.0.0.1, localhost, or ::1
    so a rogue local process cannot navigate the privileged webview to an
    arbitrary URL via the reload socket.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


class _WindowApi:
    """Python API exposed to JavaScript for window controls."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._api_pid = 0
        self._instance: InstanceController | None = None
        self._base_url: str = ''

    def bind(self, window: webview.Window, api_pid: int = 0,
             instance: InstanceController | None = None,
             base_url: str = '') -> None:
        self._window = window
        self._api_pid = api_pid
        self._instance = instance
        self._base_url = base_url.rstrip('/')

    def _get_running_evaluation(self) -> dict | None:
        """Return the first non-stale running evaluation job, or None.

        Cross-checks each running job's ``outputProject`` against the
        ``/api/projects`` list. A "running" record whose project no
        longer exists (e.g. the project was deleted, or the API was
        restarted while a job was mid-scan) is treated as stale and
        ignored — otherwise the close dialog would pop up on shutdown
        even when the user has no actual evaluation in flight.

        Any failure fetching the projects list falls back to the
        previous behavior (returning the first running job), so a
        transient endpoint glitch can't accidentally suppress the
        dialog during a real evaluation.
        """
        if not self._base_url:
            return None
        try:
            req = urllib.request.Request(f"{self._base_url}/api/evaluations")
            with urllib.request.urlopen(req, timeout=_EVAL_CHECK_TIMEOUT_S) as resp:
                jobs = json.loads(resp.read())
        except Exception:
            return None
        running = [
            j for j in (jobs if isinstance(jobs, list) else [])
            if isinstance(j, dict) and j.get("status") == "running"
        ]
        if not running:
            return None
        try:
            projects_req = urllib.request.Request(f"{self._base_url}/api/projects")
            with urllib.request.urlopen(projects_req, timeout=_EVAL_CHECK_TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            projects = (
                data.get("projects", []) if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            )
            project_ids = {p.get("id") for p in projects if isinstance(p, dict)}
        except Exception:
            return running[0]
        for j in running:
            project = j.get("outputProject") or j.get("project")
            # Jobs without an ``outputProject`` are very-early-phase
            # evals that haven't registered an output yet — keep
            # treating those as valid.
            if not project or project in project_ids:
                return j
        return None

    def _cancel_evaluation(self, job_id: str | None) -> None:
        """Issue DELETE /api/evaluations/<job_id> to stop a running scan.

        The API enforces an Origin header to reject cross-site requests, so set
        it explicitly to the dashboard base URL; without it the call 403s and
        silently no-ops. Best-effort: any failure is swallowed so a close is
        never blocked by a failed cancel.
        """
        if not job_id or not self._base_url:
            return
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/evaluations/{urllib.parse.quote(job_id)}",
                method="DELETE",
                headers={"Origin": self._base_url},
            )
            # Give the API time to SIGTERM the scan and respond; the 0.5s used
            # for the eval-check poll is too tight here.
            with urllib.request.urlopen(req, timeout=5.0):
                pass
        except Exception:
            # Best-effort: a failed cancel must never block the close, but log it
            # so a silently-uncancelled scan is at least diagnosable.
            _logger.warning("cancel-on-quit for job %s failed", job_id, exc_info=True)

    def open_browser(self, path: str = '/') -> None:
        """Open a dashboard path or an absolute web URL in the default browser.

        Absolute http(s) URLs (e.g. the update banner's GitHub release link)
        pass through untouched; anything else is treated as a path on the
        local dashboard origin, which also neutralizes non-web schemes.
        """
        if path.startswith(('http://', 'https://')):
            webbrowser.open(path)
            return
        url = self._base_url + path if self._base_url else path
        webbrowser.open(url)

    def download_url(self, path: str, filename: str) -> bool:
        """Fetch a URL from the API and save it via native Save dialog."""
        if not self._window or not self._base_url:
            return False
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else '*'
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=filename,
            file_types=(f'{ext.upper()} files (*.{ext})', 'All files (*.*)'),
        )
        if not result:
            return False
        save_path = result if isinstance(result, str) else result[0] if result else None
        if not save_path:
            return False
        try:
            url = self._base_url + path
            with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
                Path(save_path).write_bytes(resp.read())
            return True
        except (OSError, Exception):
            return False

    def save_file(self, content: str, filename: str) -> bool:
        """Open a native Save dialog and write content to the chosen path."""
        if not self._window:
            return False
        ext = filename.rsplit('.', 1)[-1] if '.' in filename else '*'
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=filename,
            file_types=(f'{ext.upper()} files (*.{ext})', 'All files (*.*)'),
        )
        if not result:
            return False
        path = result if isinstance(result, str) else result[0] if result else None
        if not path:
            return False
        try:
            Path(path).write_text(content, encoding='utf-8')
            return True
        except OSError:
            return False

    def set_titlebar_theme(self, mode: str) -> None:
        """Match the native titlebar to the active quodeq theme.

        mode is 'dark' or 'light'; any other value is ignored. Safe no-op
        before the native window handle exists — the frontend re-calls on
        pywebviewready. Linux titlebars are window-manager controlled, so
        this is a no-op there.
        """
        if mode not in ("dark", "light"):
            return
        dark = mode == "dark"
        if sys.platform == "darwin":
            _set_macos_titlebar_appearance(self._window, dark)
        elif sys.platform == "win32":
            _set_windows_titlebar(dark)



def _kill_api(pid: int) -> None:
    """Terminate the Flask API process."""
    try:
        sig = signal.SIGTERM if sys.platform != "win32" else signal.CTRL_BREAK_EVENT
        os.kill(pid, sig)
    except (OSError, ProcessLookupError):
        pass


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


_APP_DISPLAY_NAME = "quodeq"


_macos_app_icon: object | None = None  # cache the NSImage across _set calls


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
    global _macos_app_icon
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
    except (AttributeError, TypeError):
        pass
    path = _icon_path(".icns")
    if not path:
        return
    try:
        icon = NSImage.alloc().initWithContentsOfFile_(path)
    except (AttributeError, ValueError):
        icon = None
    if not icon:
        return
    _macos_app_icon = icon  # keep a live reference for the About-panel override
    try:
        NSApplication.sharedApplication().setApplicationIconImage_(icon)
    except (AttributeError, ValueError):
        pass
    # Override the default About panel so it shows our icon + name. The
    # standard panel reads from Info.plist and ignores setApplicationIconImage_
    # for non-bundled apps, so we wire a custom action on the first-responder
    # chain using orderFrontStandardAboutPanelWithOptions_.
    _install_about_panel_override()


_about_target: object | None = None  # keep delegate alive for the menu item's weak ref
_about_override_installed = False  # the _AboutHandler ObjC class may only be defined once
_help_target: object | None = None  # keep the Help-menu handler alive (menu item holds a weak ref)
_help_menu_installed = False  # the _HelpHandler ObjC class may only be defined once
_macos_toolbar_installed = False  # the unified toolbar (taller titlebar) is added once
_macos_fullscreen_observer: object | None = None  # keep the ObjC observer alive
_macos_fullscreen_observer_installed = False  # register the notifications once
_macos_fullscreen_handler_class = None  # the ObjC handler class is defined once per process


def _diag_path() -> Path:
    return Path.home() / ".quodeq" / "run" / "webview_debug.log"


try:
    _diag_path().parent.mkdir(parents=True, exist_ok=True)
    _diag = _diag_path().open("a", encoding="utf-8")  # noqa: SIM115 — lives for the process
except OSError:
    _diag = sys.stderr

_QUODEQ_WEBSITE = "https://quodeq.com"
_QUODEQ_REPO = "https://github.com/quodeq/quodeq"


def _quodeq_version() -> str:
    try:
        from importlib.metadata import version  # noqa: PLC0415
        return version("quodeq")
    except Exception:  # noqa: BLE001 — metadata may be missing in dev
        return "dev"


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
            attrs = {}
            if link:
                url = NSURL.URLWithString_(link)
                if url is not None:
                    attrs = {"NSLink": url}
            fragment = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            body.appendAttributedString_(fragment)
        _append(_QUODEQ_WEBSITE, _QUODEQ_WEBSITE)
        _append("\n")
        _append(_QUODEQ_REPO, _QUODEQ_REPO)
        return body
    except (AttributeError, ValueError):
        return None


def _install_about_panel_override() -> None:
    """Point the Apple-menu 'About …' at a handler that shows a rich panel.

    The app main menu is built lazily by NSApp during the Cocoa run loop.
    On the first call from the `loaded` event it's typically still nil, so
    schedule a repeating NSTimer that retries until the About item exists
    (or we give up after ~5s).

    Installs at most once: the ``_AboutHandler`` ObjC class can only be
    defined once per process, so a second call (e.g. on a repeat ``loaded``
    event) would raise ``objc.error`` and abort the caller.
    """
    global _about_target, _about_override_installed
    if _about_override_installed:
        return
    try:
        from AppKit import NSApplication, NSObject  # type: ignore[import-untyped]
        from Foundation import NSTimer  # type: ignore[import-untyped]
    except ImportError:
        return
    _about_override_installed = True

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
            if _macos_app_icon is not None:
                opts["ApplicationIcon"] = _macos_app_icon
            credits = _build_about_credits()
            if credits is not None:
                opts["Credits"] = credits
            NSApplication.sharedApplication().orderFrontStandardAboutPanelWithOptions_(opts)

    _about_target = _AboutHandler.alloc().init()
    state = {"attempts": 0, "timer": None}
    max_attempts = 25  # ~5 seconds at 200ms

    class _InstallPoller(NSObject):
        def tryInstall_(self, timer):  # noqa: ARG002
            state["attempts"] += 1
            app = NSApplication.sharedApplication()
            main_menu = app.mainMenu()
            if main_menu is None or main_menu.numberOfItems() == 0:
                if state["attempts"] >= max_attempts:
                    print(f"[quodeq-about] gave up after {state['attempts']} attempts — no main menu",
                          file=_diag, flush=True)
                    if state["timer"]:
                        state["timer"].invalidate()
                return
            about_items = []
            for mi in range(main_menu.numberOfItems()):
                sub = main_menu.itemAtIndex_(mi).submenu()
                if sub is None:
                    continue
                for i in range(sub.numberOfItems()):
                    item = sub.itemAtIndex_(i)
                    title = str(item.title() or "")
                    if title.lower().startswith("about"):
                        about_items.append(item)
            if not about_items:
                if state["attempts"] >= max_attempts:
                    print(f"[quodeq-about] gave up — no About item found after {state['attempts']} attempts",
                          file=_diag, flush=True)
                    if state["timer"]:
                        state["timer"].invalidate()
                return
            for item in about_items:
                item.setTarget_(_about_target)
                item.setAction_("showAbout:")
            print(f"[quodeq-about] retargeted {len(about_items)} About item(s) on attempt {state['attempts']}",
                  file=_diag, flush=True)
            if state["timer"]:
                state["timer"].invalidate()

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


# Payload both native shells dispatch to open the help tab; routed by the
# React useNativeNavBridge hook (detail must be a KNOWN_TABS entry).
_NAVIGATE_HELP_JS = "window.dispatchEvent(new CustomEvent('quodeq:navigate', { detail: 'help' }))"


def _install_macos_help_menu(window: object) -> None:
    """Add a top-level Help menu whose item opens the dashboard help tab.

    pywebview's Cocoa backend builds the main menu lazily during the run
    loop, so (like the About override) poll with an NSTimer until the menu
    bar exists, then append a "Help" menu and register it via
    NSApp.setHelpMenu_ so macOS adds its built-in search field.

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
        from AppKit import NSApplication, NSMenu, NSMenuItem, NSObject  # type: ignore[import-untyped]
        from Foundation import NSTimer  # type: ignore[import-untyped]
    except ImportError:
        return
    _help_menu_installed = True

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

    _help_target = _HelpHandler.alloc().init()
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
                    if state["timer"]:
                        state["timer"].invalidate()
                return
            help_menu = NSMenu.alloc().initWithTitle_("Help")
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "quodeq Help", "openHelp:", "?",
            )
            item.setTarget_(_help_target)
            help_menu.addItem_(item)
            top_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Help", None, "")
            top_item.setSubmenu_(help_menu)
            main_menu.addItem_(top_item)
            # Registering as THE help menu makes macOS append its native
            # search field and keeps the menu in the canonical last slot.
            app.setHelpMenu_(help_menu)
            print(f"[quodeq-help] installed Help menu on attempt {state['attempts']}",
                  file=_diag, flush=True)
            if state["timer"]:
                state["timer"].invalidate()

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


def _apply_macos_fullscreen_chrome(
    window: object, is_full: bool, *, restore_toolbar: bool = True,
) -> None:
    """Reflect fullscreen state in both the native and the web chrome.

    In fullscreen macOS draws the unified toolbar as a persistent empty gray
    bar across the top (the traffic lights it centers are hidden there), so
    drop the toolbar in fullscreen and restore it windowed. Either way toggle
    the `macos-fullscreen` CSS class, which also clears the topbar border and
    the now-pointless traffic-light reservation.

    The AppKit toolbar work runs inline — callers are on the UI thread (the
    fullscreen notifications fire there) — while the JS class toggle is
    dispatched off it (evaluate_js deadlocks on the main thread).

    ``restore_toolbar=False`` skips re-adding the toolbar when windowed; the
    initial install (_set_macos_unified_toolbar) already owns that, so the
    load-time sync must not add a second one.
    """
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is not None:
        try:
            if is_full:
                nswindow.setToolbar_(None)
            elif restore_toolbar:
                _apply_unified_toolbar(nswindow)
        except (AttributeError, ValueError, TypeError, ImportError):
            pass
    _set_macos_fullscreen_class(window, is_full)


def _install_macos_fullscreen_observer(window: object) -> None:
    """React to native fullscreen transitions so the chrome stays clean.

    On enter/exit fullscreen, drop/restore the unified toolbar (macOS otherwise
    leaves an empty gray toolbar bar at the top) and toggle a `macos-fullscreen`
    class on <html> (CSS then drops the topbar border and the traffic-light
    reservation). See _apply_macos_fullscreen_chrome.

    Uses NSWindow fullscreen notifications because they are the only reliable
    signal: on a notched display a zoomed window and a fullscreen window report
    identical inner/screen heights, so a JS heuristic can't tell them apart.

    Registers the notifications once (the ObjC observer class may only be
    defined a single time per process) but re-syncs the current state on every
    call, so reloading the page while fullscreen keeps the chrome correct (the
    notifications only fire on transitions). No-op off macOS or before the
    native handle exists. Call from the ``loaded`` event.
    """
    global _macos_fullscreen_handler_class
    if sys.platform != "darwin":
        return
    try:
        import AppKit  # noqa: PLC0415
        from Foundation import NSNotificationCenter  # noqa: PLC0415
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is None:
        return

    # Define the ObjC handler class at most once: redefining an NSObject
    # subclass in the same process raises objc.error (the same trap the About
    # panel hit). It closes over this window, of which there is only one.
    if _macos_fullscreen_handler_class is None:
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

        _macos_fullscreen_handler_class = _FullScreenHandler

    def _apply() -> None:
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

    AppHelper.callAfter(_apply)


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


def _set_app_icon() -> None:
    """Set the application icon (dock on macOS, taskbar on Windows)."""
    if sys.platform == "darwin":
        _set_macos_app_identity()
    elif sys.platform == "win32":
        try:
            import ctypes
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
        except (AttributeError, OSError):
            pass


def _make_on_reload(window: object) -> "Callable[[str], None]":
    """Return the ``_on_reload`` handler bound to *window*.

    Extracted from ``main()`` so the test suite can import and exercise the
    real implementation rather than a hand-rolled duplicate.
    """
    def _on_reload(new_url: str) -> None:
        if not _is_safe_reload_url(new_url):
            _logger.warning("Ignoring unsafe reload URL: %s", new_url)
            return
        window.load_url(new_url)  # type: ignore[union-attr]
        window.on_top = True  # type: ignore[union-attr]
        window.on_top = False  # type: ignore[union-attr]

    return _on_reload


def _webview_user_agent() -> str:
    """Browser-recognisable UA carrying the webview marker.

    The AppleWebKit/Safari tokens keep Google Fonts serving woff2; the
    marker tells the API to relax the CSP (see _WEBVIEW_UA_MARKER).
    """
    return (
        "Mozilla/5.0 (quodeq) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        f"{_WEBVIEW_UA_MARKER}/{_quodeq_version()} Safari/605.1.15"
    )


def _create_window(url: str, api: "_WindowApi") -> "webview.Window":
    """Create the dashboard window.

    macOS uses a frameless window so NSFullSizeContentView lets the app's
    topbar run under the titlebar; the native traffic lights are re-shown over
    it (see _show_macos_traffic_lights) for a unified look, and the topbar acts
    as the drag region via the ``pywebview-drag-region`` class. Windows and
    Linux use native OS chrome.

    easy_drag is disabled so only the topbar drags the window — otherwise it
    would hijack the resize splitter (a plain <div>).
    """
    return webview.create_window(
        "quodeq", url, width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT,
        frameless=(sys.platform == "darwin"), easy_drag=False,
        background_color=_WINDOW_BG_COLOR, hidden=True, js_api=api,
    )


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
        import AppKit  # noqa: PLC0415
        from PyObjCTools import AppHelper  # noqa: PLC0415
    except ImportError:
        return "keep"
    result = {"choice": "keep"}
    done = threading.Semaphore(0)

    def _show() -> None:
        try:
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

    AppHelper.callAfter(_show)
    done.acquire()
    return result["choice"]


def _ask_close_choice(window: object) -> str:
    """Ask the user how to close while a scan runs; return 'keep', 'cancel', or 'stay'.

    macOS gets a 3-button native alert (keep scanning / cancel scan / stay);
    other backends get pywebview's 2-button dialog (OK = keep scanning, Cancel =
    stay). If the dialog can't render, return 'keep' so the user is never
    trapped in an un-closeable window.
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


def _make_on_closing(api: "_WindowApi", window: object) -> "Callable[[], bool]":
    """Native close handler: confirm via a native dialog if a scan is running.

    The scan is a separate process, so quitting just closes the window and the
    scan keeps running — unless the user picks "Cancel scan and quit" (macOS),
    which stops it first.

    pywebview's ``closing`` event is a *locking* event: its handler runs
    synchronously on the GUI thread (on macOS, inside ``windowShouldClose:``).
    How the confirmation dialog can be shown from there depends on the backend:

    * macOS / GTK / Qt — the native dialog marshals back onto the GUI thread and
      then blocks its caller on a semaphore. Called from the GUI-thread closing
      handler it self-deadlocks (the alert can never run — the GUI thread is
      parked in the handler), which froze the window whenever a scan was in
      flight. So we don't answer inline: veto the close (return False), show the
      dialog on a worker thread (off the GUI thread the semaphore is safe), and
      re-issue the close via ``window.destroy`` once the user confirms.

    * Windows — winforms' ``create_confirmation_dialog`` is a *direct* modal
      ``MessageBox.Show`` with no GUI-thread marshaling. Showing it from a
      worker thread would make it ownerless and non-modal, so on Windows we show
      it inline on the (already UI-thread) closing handler and answer
      synchronously. winforms doesn't self-block, so there is no deadlock.
    """
    if sys.platform == "win32":
        return _make_on_closing_inline(api, window)
    return _make_on_closing_async(api, window)


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
    (``_prompt_and_close``). Dict-item writes are atomic under the GIL; the
    running job id is passed to the worker as an argument (not shared) so a
    re-entrant close can't make it cancel a different job. ``prompting`` stays
    set until the worker either resolves to 'stay' (which clears it, allowing a
    later re-prompt) or commits to closing (``confirmed``), so exactly one prompt
    is ever in flight — even across the possibly-slow cancel call.
    """
    state = {"prompting": False, "confirmed": False}

    def _prompt_and_close(job_id: str | None) -> None:
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
        # (On macOS destroy() bypasses windowShouldClose:, so the guard is inert
        # there — but do not reorder this to "after destroy succeeds", it would
        # reintroduce the re-entry loop on the other backends.) `prompting` is
        # deliberately left set through the cancel call above so a second close
        # during that window can't pop a duplicate dialog.
        state["confirmed"] = True
        try:
            window.destroy()  # type: ignore[union-attr]
        except Exception:
            _logger.debug("window.destroy after close-confirm failed", exc_info=True)

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
            worker = threading.Thread(
                target=_prompt_and_close, args=(job_id,), daemon=True,
            )
            _on_closing._worker = worker  # type: ignore[attr-defined]
            worker.start()
        return False  # veto now; the worker re-closes the window if confirmed

    _on_closing._worker = None  # type: ignore[attr-defined]
    return _on_closing


def main() -> None:
    _set_app_icon()
    url = sys.argv[1]
    sock_path = Path(sys.argv[2])
    api_pid = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0

    instance = InstanceController(sock_path)
    api = _WindowApi()

    window = _create_window(url, api)
    api.bind(window, api_pid=api_pid, instance=instance, base_url=url)

    _on_reload = _make_on_reload(window)

    def _on_loaded() -> None:
        window.show()
        if sys.platform == "darwin":
            # Show the native traffic lights FIRST: they are the only window
            # controls on the frameless macOS window, so they must not be
            # skipped if the best-effort app-identity setup below raises.
            _show_macos_traffic_lights(window)
            _set_macos_unified_toolbar(window)
            _set_macos_titlebar_appearance(window, True)
            # Reflect fullscreen state in a CSS class so the topbar border and
            # the traffic-light reservation drop when macOS hides the lights.
            _install_macos_fullscreen_observer(window)
            # Re-apply the dock icon + bundle name now that pywebview's
            # NSApplication is live (the early call in main() targets the
            # pre-pywebview NSApp). Best-effort — never block the controls.
            try:
                _set_macos_app_identity()
            except Exception:
                _logger.debug("macOS app-identity setup failed", exc_info=True)
            # Native Help menu → dashboard help tab. Best-effort like the
            # identity setup: a failure must never block window chrome.
            try:
                _install_macos_help_menu(window)
            except Exception:
                _logger.debug("macOS Help menu setup failed", exc_info=True)
        elif sys.platform == "win32":
            _set_windows_titlebar(True)

    window.events.loaded += _on_loaded
    window.events.closing += _make_on_closing(api, window)

    instance.start_listening(on_reload=_on_reload)

    storage_dir = str(_quodeq_dir() / "webview")

    try:
        webview.start(private_mode=False, storage_path=storage_dir,
                      user_agent=_webview_user_agent(),
                      menu=_non_macos_menu(window) or [])
    finally:
        instance.shutdown()
        if api_pid:
            _kill_api(api_pid)


if __name__ == "__main__":
    main()
