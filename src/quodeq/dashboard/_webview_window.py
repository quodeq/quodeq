"""PyWebView window process — launched as a subprocess by _server.py.

tests/dashboard/test_native_chrome.py patches some internals via
``patch.object(ww, "<name>")`` while a DIFFERENT function bare-calls the
patched name. ``patch.object(ww, "X")`` only rebinds the name ``X`` inside
*this* module's namespace — so whichever function bare-calls ``X`` must be
defined here (its ``__globals__`` must be this module's dict), or the mock
never intercepts the call. The remaining seams of that kind are ``webview``,
``InstanceController``, the ``_make_on_*`` factories, ``_create_window``,
``_quodeq_dir``, ``_set_app_icon``, and ``_non_macos_menu`` — all bare-called
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

from quodeq.dashboard._build_npm import _quodeq_dir
from quodeq.dashboard._instance import InstanceController
from quodeq.dashboard._webview_token import read_token_from_stdin
from quodeq.dashboard._webview_window_about import (  # noqa: F401 — re-export
    _set_app_icon,
    _set_macos_app_identity,
    _webview_user_agent,
    _WEBVIEW_UA_MARKER,
)
from quodeq.dashboard import _webview_window_chrome as _chrome
from quodeq.dashboard._webview_window_chrome import (  # noqa: F401 — re-export
    _apply_unified_toolbar,
    _set_macos_fullscreen_class,
    _set_macos_titlebar_appearance,
    _set_windows_titlebar,
    _show_macos_traffic_lights,
)
from quodeq.dashboard._webview_window_close import (  # noqa: F401 — re-export
    _alert_return_to_choice,
    _ask_close_choice,
    _CLOSE_CONFIRM_BODY,
    _CLOSE_CONFIRM_TITLE,
    _macos_confirm_close,
    _make_on_closing,
    _prompt_close_choice_and_finish,
)
from quodeq.dashboard._webview_window_fullscreen import (  # noqa: F401 — re-export
    _install_macos_fullscreen_observer,
)
from quodeq.dashboard._webview_window_help_menu import (  # noqa: F401 — re-export
    _NAVIGATE_HELP_JS,
    _non_macos_menu,
)
from quodeq.dashboard._webview_window_lifecycle import _make_on_loaded
from quodeq.dashboard._webview_window_native_ops import (  # noqa: F401 — re-export
    _download_via_dialog,
    _fetch_running_evaluation,
    _is_safe_reload_url,
    _kill_api,
    _make_on_reload,
    _save_via_dialog,
    _send_cancel_evaluation,
)

_logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
_WINDOW_BG_COLOR = '#0d1117'


class _WindowApi:
    """Python API exposed to JavaScript for window controls.

    HTTP and native-dialog bodies live in _webview_window_native_ops.py
    (none of them are patch-tested by name); set_titlebar_theme dispatches
    through _webview_window_chrome (imported here as _chrome), so a patch on
    either module's copy of _set_macos_titlebar_appearance / _set_windows_titlebar
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
        return _fetch_running_evaluation(self._base_url)

    def _cancel_evaluation(self, job_id: str | None) -> None:
        _send_cancel_evaluation(self._base_url, job_id)

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
        return _download_via_dialog(self._window, self._base_url, path, filename)

    def save_file(self, content: str, filename: str) -> bool:
        return _save_via_dialog(self._window, content, filename)

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
            _chrome._set_macos_titlebar_appearance(self._window, dark)
        elif sys.platform == "win32":
            _chrome._set_windows_titlebar(dark)


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


def _apply_macos_fullscreen_chrome(
    window: object, is_full: bool, *, restore_toolbar: bool = True,
) -> None:
    """Reflect fullscreen state in both the native and the web chrome.

    In fullscreen macOS draws the unified toolbar as a persistent empty gray
    bar across the top (the traffic lights it centers are hidden there), so
    drop the toolbar in fullscreen and restore it windowed. Either way toggle
    the `macos-fullscreen` CSS class, which also clears the topbar border and
    the now-pointless traffic-light reservation.

    ``restore_toolbar=False`` skips re-adding the toolbar when windowed; the
    initial install (_set_macos_unified_toolbar) already owns that, so the
    load-time sync must not add a second one.

    Calls through _webview_window_chrome (imported here as _chrome) for
    _apply_unified_toolbar, so a patch on either module's copy is visible.
    """
    nswindow = getattr(window, "native", None) if window is not None else None
    if nswindow is not None:
        try:
            if is_full:
                nswindow.setToolbar_(None)
            elif restore_toolbar:
                _chrome._apply_unified_toolbar(nswindow)
        except (AttributeError, ValueError, TypeError, ImportError):
            pass
    _set_macos_fullscreen_class(window, is_full)


def main() -> None:
    _set_app_icon()
    url = sys.argv[1]
    sock_path = Path(sys.argv[2])
    api_pid = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
    webview_token = read_token_from_stdin()

    instance = InstanceController(sock_path)
    api = _WindowApi()

    window = _create_window(url, api)
    api.bind(window, api_pid=api_pid, instance=instance, base_url=url)

    _on_reload = _make_on_reload(window)

    window.events.loaded += _make_on_loaded(window)
    window.events.closing += _make_on_closing(api, window)

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
        instance.start_listening(on_reload=_on_reload)

    storage_dir = str(_quodeq_dir() / "webview")

    try:
        webview.start(private_mode=False, storage_path=storage_dir,
                      user_agent=_webview_user_agent(webview_token),
                      menu=_non_macos_menu(window) or [])
    finally:
        instance.shutdown()
        if api_pid:
            _kill_api(api_pid)


if __name__ == "__main__":
    main()
