"""PyWebView window process — launched as a subprocess by _server.py.

tests/dashboard/test_native_chrome.py patches some internals via
``patch.object(ww, "<name>")`` while a DIFFERENT function bare-calls the
patched name. ``patch.object(ww, "X")`` only rebinds the name ``X`` inside
*this* module's namespace — so whichever function bare-calls ``X`` must be
defined here (its ``__globals__`` must be this module's dict), or the mock
never intercepts the call. The remaining seams of that kind are ``webview``,
``InstanceController``, the ``make_on_*`` factories, ``_create_window``,
``quodeq_dir``, ``set_app_icon``, and ``non_macos_menu`` — all bare-called
from main() (or, for ``webview``, also from _create_window), defined here or
merely re-exported from a sibling module. ``sys`` and ``webbrowser`` are
patched as shared module objects instead (e.g.
``patch.object(ww.sys, "platform")``), which works regardless of which file
calls them.
"""
from __future__ import annotations

import logging
import sys
import webbrowser
from pathlib import Path

import webview

from quodeq.dashboard._build_npm import quodeq_dir
from quodeq.dashboard._instance import InstanceController
from quodeq.dashboard._webview_token import read_token_from_stdin
from quodeq.dashboard._webview_window_about import (  # noqa: F401 — re-export
    set_app_icon,
    set_macos_app_identity,
    webview_user_agent,
    WEBVIEW_UA_MARKER,
)
from quodeq.dashboard import _webview_window_chrome as _chrome
from quodeq.dashboard._webview_window_chrome import (  # noqa: F401 — re-export
    apply_unified_toolbar,
    set_macos_fullscreen_class,
    set_macos_titlebar_appearance,
    set_windows_titlebar,
    show_macos_traffic_lights,
)
from quodeq.dashboard._webview_window_close import (  # noqa: F401 — re-export
    alert_return_to_choice,
    ask_close_choice,
    CLOSE_CONFIRM_BODY,
    CLOSE_CONFIRM_TITLE,
    macos_confirm_close,
    make_on_closing,
    prompt_close_choice_and_finish,
)
from quodeq.dashboard._webview_window_fullscreen import (  # noqa: F401 — re-export
    install_macos_fullscreen_observer,
)
from quodeq.dashboard._webview_window_help_menu import (  # noqa: F401 — re-export
    NAVIGATE_HELP_JS,
    non_macos_menu,
)
from quodeq.dashboard._webview_window_lifecycle import make_on_loaded
from quodeq.dashboard._webview_window_native_ops import (  # noqa: F401 — re-export
    download_via_dialog,
    fetch_running_evaluation,
    is_safe_reload_url,
    kill_api,
    make_on_reload,
    save_via_dialog,
    send_cancel_evaluation,
)

_logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
_WINDOW_BG_COLOR = '#0d1117'
_ARGV_API_PID = 3  # optional argv slot: pid of the API process to watch


class WindowApi:
    """Python API exposed to JavaScript for window controls.

    HTTP and native-dialog bodies live in _webview_window_native_ops.py
    (none of them are patch-tested by name); set_titlebar_theme dispatches
    through _webview_window_chrome (imported here as _chrome), so a patch on
    either module's copy of set_macos_titlebar_appearance / set_windows_titlebar
    is visible to the call.
    """

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
        return fetch_running_evaluation(self._base_url)

    def _cancel_evaluation(self, job_id: str | None) -> None:
        send_cancel_evaluation(self._base_url, job_id)

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
        return download_via_dialog(self._window, self._base_url, path, filename)

    def save_file(self, content: str, filename: str) -> bool:
        return save_via_dialog(self._window, content, filename)

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
            _chrome.set_macos_titlebar_appearance(self._window, dark)
        elif sys.platform == "win32":
            _chrome.set_windows_titlebar(dark)


def _create_window(url: str, api: "WindowApi") -> "webview.Window":
    """Create the dashboard window.

    macOS uses a frameless window so NSFullSizeContentView lets the app's
    topbar run under the titlebar; the native traffic lights are re-shown over
    it (see show_macos_traffic_lights) for a unified look, and the topbar acts
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


def apply_macos_fullscreen_chrome(
    window: object, is_full: bool, *, restore_toolbar: bool = True,
) -> None:
    """Reflect fullscreen state in both the native and the web chrome.

    In fullscreen macOS draws the unified toolbar as a persistent empty gray
    bar across the top (the traffic lights it centers are hidden there), so
    drop the toolbar in fullscreen and restore it windowed. Either way toggle
    the `macos-fullscreen` CSS class, which also clears the topbar border and
    the now-pointless traffic-light reservation.

    ``restore_toolbar=False`` skips re-adding the toolbar when windowed; the
    initial install (set_macos_unified_toolbar) already owns that, so the
    load-time sync must not add a second one.

    Calls through _webview_window_chrome (imported here as _chrome) for
    apply_unified_toolbar, so a patch on either module's copy is visible.
    """
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is not None:
        try:
            if is_full:
                nswindow.setToolbar_(None)
            elif restore_toolbar:
                _chrome.apply_unified_toolbar(nswindow)
        except (AttributeError, ValueError, TypeError, ImportError) as exc:
            _logger.debug("macOS fullscreen chrome not applied: %s", exc)
    set_macos_fullscreen_class(window, is_full)


def _parse_argv() -> tuple[str, Path, int]:
    """``(url, sock_path, api_pid)`` from argv; the api pid slot is optional (0 when absent)."""
    url = sys.argv[1]
    sock_path = Path(sys.argv[2])
    api_pid = (int(sys.argv[_ARGV_API_PID])
               if len(sys.argv) > _ARGV_API_PID and sys.argv[_ARGV_API_PID] else 0)
    return url, sock_path, api_pid


def _wire_window(url: str, sock_path: Path, api_pid: int) -> tuple[webview.Window, InstanceController]:
    """Create the window, bind its JS API and hook the lifecycle events."""
    instance = InstanceController(sock_path)
    api = WindowApi()
    window = _create_window(url, api)
    api.bind(window, api_pid=api_pid, instance=instance, base_url=url)
    window.events.loaded += make_on_loaded(window)
    window.events.closing += make_on_closing(api, window)
    return window, instance


def _own_reload_socket(instance: InstanceController, window: webview.Window) -> None:
    # Own the reload socket here, not in the parent: this process holds the
    # window, so it is the only one that can bring it forward on a relaunch.
    # try_acquire is what binds the socket — without it start_listening has
    # nothing to accept on.
    if not instance.try_acquire():
        _logger.warning(
            "Another instance owns %s — this window will not answer reloads",
            instance.sock_path,
        )
    else:
        instance.start_listening(on_reload=make_on_reload(window))


def _run_webview(window: webview.Window, webview_token: str, instance: InstanceController,
                 api_pid: int) -> None:
    """Block in the webview loop; release the socket and the API process on exit."""
    storage_dir = str(quodeq_dir() / "webview")
    try:
        webview.start(private_mode=False, storage_path=storage_dir,
                      user_agent=webview_user_agent(webview_token),
                      menu=non_macos_menu(window) or [])
    finally:
        instance.shutdown()
        if api_pid:
            kill_api(api_pid)


def main() -> None:
    set_app_icon()
    url, sock_path, api_pid = _parse_argv()
    webview_token = read_token_from_stdin()
    window, instance = _wire_window(url, sock_path, api_pid)
    _own_reload_socket(instance, window)
    _run_webview(window, webview_token, instance, api_pid)


if __name__ == "__main__":
    main()
