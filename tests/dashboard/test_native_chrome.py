"""Native-chrome window: creation args, custom UA, marker drift guard and titlebar theme."""
import inspect
import io

from unittest.mock import MagicMock, patch

import webview as real_webview

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard import _webview_window_chrome as chrome


class TestWindowCreation:
    def _kwargs_for_platform(self, platform):
        with patch.object(ww.sys, "platform", platform), patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", MagicMock())
        wv.create_window.assert_called_once()
        return wv.create_window.call_args.kwargs

    def test_frameless_on_macos_for_unified_titlebar(self):
        # macOS goes frameless so NSFullSizeContentView lets the topbar run
        # under the titlebar (the unified look).
        assert self._kwargs_for_platform("darwin")["frameless"] is True

    def test_native_chrome_off_macos(self):
        assert self._kwargs_for_platform("win32")["frameless"] is False
        assert self._kwargs_for_platform("linux")["frameless"] is False

    def test_easy_drag_disabled(self):
        # Only the topbar (pywebview-drag-region) drags the window.
        assert self._kwargs_for_platform("darwin")["easy_drag"] is False

    def test_js_api_bound(self):
        api = MagicMock()
        with patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", api)
        assert wv.create_window.call_args.kwargs["js_api"] is api

    def test_create_window_only_passes_supported_kwargs(self):
        """Guard against passing a kwarg the installed pywebview's
        create_window does not accept. user_agent, for example, belongs to
        webview.start(), not create_window() — passing it here crashes the
        window process at launch (a MagicMock would silently accept it, so
        we check against the real signature)."""
        captured = {}
        with patch.object(ww, "webview") as wv:
            wv.create_window.side_effect = lambda *a, **k: captured.update(k) or MagicMock()
            ww._create_window("http://127.0.0.1:7863", MagicMock())
        allowed = set(inspect.signature(real_webview.create_window).parameters)
        unsupported = set(captured) - allowed
        assert not unsupported, f"create_window kwargs not supported by pywebview: {unsupported}"

    def test_webview_user_agent_is_a_start_kwarg(self):
        """The marker UA must be delivered via webview.start(user_agent=...);
        confirm the installed pywebview's start() accepts it."""
        assert "user_agent" in inspect.signature(real_webview.start).parameters


class TestUaMarkerNoDrift:
    def test_marker_matches_security_module(self):
        from quodeq.api import security
        assert ww.WEBVIEW_UA_MARKER == security._WEBVIEW_UA_MARKER

    def test_user_agent_carries_marker(self):
        assert ww.WEBVIEW_UA_MARKER in ww.webview_user_agent()

    def test_token_prefix_matches_security_module(self):
        from quodeq.api import security
        from quodeq.dashboard import _webview_window_about
        assert _webview_window_about.WEBVIEW_TOKEN_UA_PREFIX == security._WEBVIEW_TOKEN_UA_PREFIX

    def test_user_agent_without_token_has_no_token_prefix(self):
        """The marker alone is not the security check — no token, no token prefix."""
        from quodeq.dashboard import _webview_window_about
        assert _webview_window_about.WEBVIEW_TOKEN_UA_PREFIX not in ww.webview_user_agent()
        assert _webview_window_about.WEBVIEW_TOKEN_UA_PREFIX not in ww.webview_user_agent(None)

    def test_user_agent_with_token_carries_it(self):
        from quodeq.dashboard import _webview_window_about
        ua = ww.webview_user_agent("shared-secret-123")
        assert f"{_webview_window_about.WEBVIEW_TOKEN_UA_PREFIX}shared-secret-123" in ua
        assert ww.WEBVIEW_UA_MARKER in ua  # human-readable marker kept alongside the token


class TestMainThreadsWebviewToken:
    """main() must read the launch token from STDIN (never argv) and thread it
    into the UA handed to webview.start — that UA is what the API's security
    check inspects.

    Rewritten from an argv[4] version: argv is world-readable
    (/proc/<pid>/cmdline is 0444, and `ps` shows it to every user), so a token
    there let any local user forge the UA that wins the CSP 'unsafe-eval'
    relaxation. The old test asserted exactly the mechanism that was the bug.
    """

    def _run_main(self, monkeypatch, tmp_path, stdin_text, argv_tail=("",)):
        argv = ["webview.py", "http://127.0.0.1:7863", str(tmp_path / "reload.sock"), *argv_tail]
        monkeypatch.setattr(ww.sys, "argv", argv)
        monkeypatch.setattr(ww.sys, "stdin", io.StringIO(stdin_text))
        mock_instance = MagicMock()
        mock_instance.try_acquire.return_value = False
        with patch.object(ww, "set_app_icon"), \
             patch.object(ww, "InstanceController", return_value=mock_instance), \
             patch.object(ww, "_create_window", return_value=MagicMock()), \
             patch.object(ww, "make_on_reload", return_value=MagicMock()), \
             patch.object(ww, "make_on_loaded", return_value=MagicMock()), \
             patch.object(ww, "make_on_closing", return_value=MagicMock()), \
             patch.object(ww, "non_macos_menu", return_value=None), \
             patch.object(ww, "quodeq_dir", return_value=tmp_path), \
             patch.object(ww, "webview") as mock_webview:
            ww.main()
        return mock_webview.start.call_args.kwargs["user_agent"]

    def test_token_from_stdin_reaches_user_agent(self, monkeypatch, tmp_path):
        from quodeq.dashboard import _webview_window_about
        ua = self._run_main(monkeypatch, tmp_path, "shared-secret-123\n")
        assert f"{_webview_window_about.WEBVIEW_TOKEN_UA_PREFIX}shared-secret-123" in ua

    def test_empty_stdin_is_backward_compatible(self, monkeypatch, tmp_path):
        """A launcher that sends nothing (or a parent that died before the
        write) must not crash main(). The UA carries no token prefix, so the
        API serves the strict CSP -- fail closed, not fail open."""
        from quodeq.dashboard import _webview_window_about
        ua = self._run_main(monkeypatch, tmp_path, "")
        assert _webview_window_about.WEBVIEW_TOKEN_UA_PREFIX not in ua

    def test_a_token_left_in_argv_is_ignored(self, monkeypatch, tmp_path):
        """Regression guard for the fix itself.

        If someone reintroduces an argv token (or an old launcher passes one),
        it must NOT be honoured -- otherwise the world-readable path is live
        again and the stdin handover is decorative.
        """
        from quodeq.dashboard import _webview_window_about
        ua = self._run_main(
            monkeypatch, tmp_path, "", argv_tail=("", "token-from-argv"),
        )
        assert "token-from-argv" not in ua
        assert _webview_window_about.WEBVIEW_TOKEN_UA_PREFIX not in ua

    def test_stdin_wins_over_a_stale_argv_token(self, monkeypatch, tmp_path):
        from quodeq.dashboard import _webview_window_about
        ua = self._run_main(
            monkeypatch, tmp_path, "real-token\n", argv_tail=("", "token-from-argv"),
        )
        assert f"{_webview_window_about.WEBVIEW_TOKEN_UA_PREFIX}real-token" in ua
        assert "token-from-argv" not in ua


class TestSetTitlebarTheme:
    def _api(self):
        api = ww.WindowApi()
        api._window = MagicMock()
        return api

    def test_dark_dispatches_macos(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(chrome, "set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("dark")
        mac.assert_called_once_with(api._window, True)

    def test_light_dispatches_macos(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(chrome, "set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("light")
        mac.assert_called_once_with(api._window, False)

    def test_dark_dispatches_windows(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "win32"), \
             patch.object(chrome, "set_windows_titlebar") as win:
            api.set_titlebar_theme("dark")
        win.assert_called_once_with(True)

    def test_unknown_mode_is_noop(self):
        api = self._api()
        with patch.object(ww.sys, "platform", "darwin"), \
             patch.object(chrome, "set_macos_titlebar_appearance") as mac:
            api.set_titlebar_theme("purple")
        mac.assert_not_called()
