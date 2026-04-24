"""PyWebView window process — launched as a subprocess by _server.py."""
from __future__ import annotations

import html as _html
import json
import os
import signal
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import webview

from quodeq.dashboard._build_npm import _quodeq_dir
from quodeq.dashboard._instance import InstanceController
from quodeq.dashboard._webview_html import INJECT_JS, CLOSING_OVERLAY_JS

_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
_WINDOW_BG_COLOR = '#0d1117'
_CLEANUP_JOIN_TIMEOUT_S = 0.3
_EVAL_CHECK_TIMEOUT_S = 0.5
_DOWNLOAD_TIMEOUT_S = 120

# Dialog CSS layout constants
_DIALOG_PADDING = "24px 28px"
_DIALOG_BORDER_RADIUS = "12px"
_DIALOG_FONT_SIZE = "0.82rem"
_BUTTON_PADDING = "10px 16px"
_BUTTON_BORDER_RADIUS = "6px"
_BUTTON_FONT_SIZE = "0.85rem"


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

    def close(self) -> None:
        # Check for running evaluation FIRST. Don't render the closing
        # overlay yet — it covers the screen and would hide the dialog.
        job = self._get_running_evaluation() if self._window else None
        if job and self._window:
            choice = self._await_close_dialog(job)
            if choice == 'back':
                return
            if choice == 'cancel':
                self._cancel_evaluation(job.get("jobId") or job.get("job_id"))
            # Any other value (including 'keep') falls through to the exit path.

        # Show closing overlay (only reached when user actually closes).
        if self._window:
            try:
                self._window.evaluate_js(CLOSING_OVERLAY_JS)
            except Exception:
                pass

        # Cleanup and exit — run in a thread so os._exit fires fast
        def _cleanup():
            if self._api_pid:
                _kill_api(self._api_pid)
            if self._instance:
                self._instance.shutdown()
        t = threading.Thread(target=_cleanup, daemon=True)
        t.start()
        t.join(timeout=_CLEANUP_JOIN_TIMEOUT_S)
        os._exit(0)  # bypass cleanup — webview event loop would deadlock sys.exit

    def _await_close_dialog(self, job: dict, timeout_s: float = 300.0) -> str | None:
        """Render the close dialog and poll a JS global for the user's choice.

        pywebview's evaluate_js does NOT await Promises — it returns None
        immediately when given Promise-returning JS. That made the existing
        `choice = evaluate_js(dialog_js)` call return None every time, skip
        every if-branch, and fall through to os._exit. Instead, stash the
        Promise result on a global and poll until it's set.
        """
        if not self._window:
            return None
        try:
            self._window.evaluate_js(
                "window._qd_close_result = null; "
                "(" + self._build_close_dialog_js(job) + ")"
                ".then(function(r){ window._qd_close_result = r; });"
            )
        except Exception:
            return None
        import time as _time  # noqa: PLC0415
        deadline = _time.monotonic() + timeout_s
        while _time.monotonic() < deadline:
            try:
                result = self._window.evaluate_js("window._qd_close_result")
            except Exception:
                result = None
            if result:
                return str(result)
            _time.sleep(0.1)
        return None

    def _cancel_evaluation(self, job_id: str | None) -> None:
        """Issue DELETE /api/evaluations/<job_id> to stop a running scan.

        The API enforces an Origin header to reject cross-site requests; a
        missing header returns 403 which silently fails this call, so we
        set Origin explicitly to self._base_url.
        """
        if not job_id or not self._base_url:
            return
        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/evaluations/{urllib.parse.quote(job_id)}",
                method="DELETE",
                headers={"Origin": self._base_url},
            )
            # Give the API enough time to SIGTERM the scan and respond —
            # the 0.5s used for the eval-check poll is too tight here.
            with urllib.request.urlopen(req, timeout=5.0):
                pass
        except Exception:
            pass

    def _get_running_evaluation(self) -> dict | None:
        """Return the first running evaluation job, or None."""
        if not self._base_url:
            return None
        try:
            req = urllib.request.Request(f"{self._base_url}/api/evaluations")
            with urllib.request.urlopen(req, timeout=_EVAL_CHECK_TIMEOUT_S) as resp:
                jobs = json.loads(resp.read())
                for j in (jobs if isinstance(jobs, list) else []):
                    if j.get("status") == "running":
                        return j
        except Exception:
            pass
        return None

    @staticmethod
    def _build_close_dialog_js(job: dict) -> str:
        """Build JS for the close confirmation dialog with job info."""
        phase = _html.escape(job.get("phase", "analyzing"))
        dim = _html.escape(job.get("currentDimension", ""))
        repo = _html.escape(job.get("repo", ""))
        # Build info line
        info_parts = []
        if repo:
            name = _html.escape(repo.rsplit("/", 1)[-1] if "/" in repo else repo)
            info_parts.append(f"Project: <b>{name}</b>")
        if dim:
            info_parts.append(f"Dimension: <b>{dim}</b>")
        if phase:
            info_parts.append(f"Phase: <b>{phase}</b>")
        info_html = "<br>".join(info_parts) if info_parts else "Running..."

        return f"""
            (function() {{
                var d = document.createElement('div');
                d.id = '_qd_close_dialog';
                d.style.cssText = 'position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center';
                d.innerHTML = '<div style="background:var(--color-surface,#1c2128);border:1px solid var(--color-border,#333);border-radius:{_DIALOG_BORDER_RADIUS};padding:{_DIALOG_PADDING};max-width:420px;color:var(--color-text,#e6edf3);font-family:inherit">'
                    + '<h3 style="margin:0 0 12px;font-size:1rem">Evaluation in progress</h3>'
                    + '<div style="margin:0 0 16px;padding:10px 14px;background:var(--color-surface-alt,#161b22);border-radius:{_BUTTON_BORDER_RADIUS};font-size:{_DIALOG_FONT_SIZE};line-height:1.6;color:var(--color-text-muted,#8b949e)">{info_html}</div>'
                    + '<div style="display:flex;flex-direction:column;gap:8px">'
                    + '<button id="_qd_close_keep" style="padding:{_BUTTON_PADDING};border:1px solid var(--color-border,#333);border-radius:{_BUTTON_BORDER_RADIUS};background:var(--color-surface-alt,#161b22);color:var(--color-text,#e6edf3);cursor:pointer;font-size:{_BUTTON_FONT_SIZE};line-height:1.5">Close window<br><span style="opacity:0.7;font-size:0.85em">evaluation continues in background</span></button>'
                    + '<button id="_qd_close_cancel" style="padding:{_BUTTON_PADDING};border:1px solid #da3633;border-radius:{_BUTTON_BORDER_RADIUS};background:transparent;color:#f85149;cursor:pointer;font-size:{_BUTTON_FONT_SIZE}">Cancel evaluation and close</button>'
                    + '<button id="_qd_close_back" style="padding:{_BUTTON_PADDING};border:none;border-radius:{_BUTTON_BORDER_RADIUS};background:transparent;color:var(--color-text-muted,#8b949e);cursor:pointer;font-size:{_BUTTON_FONT_SIZE}">Go back</button>'
                    + '</div></div>';
                document.body.appendChild(d);
                return new Promise(function(resolve) {{
                    document.getElementById('_qd_close_keep').onclick = function() {{ d.remove(); resolve('keep'); }};
                    document.getElementById('_qd_close_cancel').onclick = function() {{ d.remove(); resolve('cancel'); }};
                    document.getElementById('_qd_close_back').onclick = function() {{ d.remove(); resolve('back'); }};
                    d.onclick = function(e) {{ if (e.target === d) {{ d.remove(); resolve('back'); }} }};
                }});
            }})()
        """

    def open_browser(self, path: str = '/') -> None:
        """Open a URL in the system default browser."""
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

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def maximize(self) -> None:
        if not self._window:
            return
        if sys.platform == "win32":
            if self._window.maximized:
                self._window.restore()
            else:
                self._window.maximize()
        else:
            self._window.toggle_fullscreen()


def _kill_api(pid: int) -> None:
    """Terminate the Flask API process."""
    try:
        sig = signal.SIGTERM if sys.platform != "win32" else signal.CTRL_BREAK_EVENT
        os.kill(pid, sig)
    except (OSError, ProcessLookupError):
        pass


def _icon_path(ext: str) -> str | None:
    """Resolve the quodeq icon path for the given extension (.icns or .ico)."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "packaging"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent.parent / "packaging"
    if ext == ".icns":
        p = base / "macos" / "icon.icns"
    elif ext == ".ico":
        p = base / "windows" / "icon.ico"
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
    """Point the Apple-menu 'About …' at a handler that shows a rich panel."""
    global _about_target
    try:
        from AppKit import NSApplication, NSObject  # type: ignore[import-untyped]
    except ImportError:
        return

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

    try:
        app = NSApplication.sharedApplication()
        main_menu = app.mainMenu()
        if main_menu is None or main_menu.numberOfItems() == 0:
            return
        app_menu = main_menu.itemAtIndex_(0).submenu()
        if app_menu is None or app_menu.numberOfItems() == 0:
            return
        about_item = app_menu.itemAtIndex_(0)  # convention: "About …" is first
        _about_target = _AboutHandler.alloc().init()
        about_item.setTarget_(_about_target)
        about_item.setAction_("showAbout:")
    except (AttributeError, IndexError, ValueError):
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


def main() -> None:
    _set_app_icon()
    url = sys.argv[1]
    sock_path = Path(sys.argv[2])
    api_pid = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0

    instance = InstanceController(sock_path)
    api = _WindowApi()

    window = webview.create_window("quodeq", url, width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT,
                                    frameless=True, easy_drag=True,
                                    background_color=_WINDOW_BG_COLOR, hidden=True,
                                    js_api=api)
    api.bind(window, api_pid=api_pid, instance=instance, base_url=url)

    def _on_reload(new_url: str) -> None:
        window.load_url(new_url)
        window.on_top = True
        window.on_top = False

    def _on_loaded() -> None:
        window.show()
        window.evaluate_js(INJECT_JS)
        # Re-apply the dock icon + bundle name now that pywebview's
        # NSApplication instance is live. Calling this earlier in main()
        # targets the pre-pywebview NSApp and gets overridden.
        if sys.platform == "darwin":
            _set_macos_app_identity()

    def _on_closing() -> bool:
        """Intercept native close (Cmd+Q, red button, window manager).

        Runs on pywebview's main thread. If a scan is running, render the
        close dialog synchronously and branch on the user's choice:
          - 'back'   → block the native close (return False)
          - 'keep'   → allow close; scan continues in background
          - 'cancel' → issue cancel API call, then allow close
        If no scan is running, allow the close without prompting.
        """
        try:
            job = api._get_running_evaluation()
        except Exception:
            job = None
        if not job:
            return True
        choice = api._await_close_dialog(job)
        if choice == 'back':
            return False
        if choice == 'cancel':
            api._cancel_evaluation(job.get("jobId") or job.get("job_id"))
        return True

    window.events.loaded += _on_loaded
    window.events.closing += _on_closing

    instance.start_listening(on_reload=_on_reload)

    storage_dir = str(_quodeq_dir() / "webview")

    try:
        webview.start(private_mode=False, storage_path=storage_dir)
    finally:
        instance.shutdown()
        if api_pid:
            _kill_api(api_pid)


if __name__ == "__main__":
    main()
