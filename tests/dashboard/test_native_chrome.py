"""Native-chrome window: creation args, custom UA, and marker drift guard."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww


class TestWindowCreation:
    def test_create_window_uses_native_chrome_and_webview_ua(self):
        api = MagicMock()
        with patch.object(ww, "webview") as wv:
            ww._create_window("http://127.0.0.1:7863", api)
        wv.create_window.assert_called_once()
        kwargs = wv.create_window.call_args.kwargs
        assert kwargs["frameless"] is False
        assert ww._WEBVIEW_UA_MARKER in kwargs["user_agent"]
        assert kwargs["js_api"] is api


class TestUaMarkerNoDrift:
    def test_marker_matches_security_module(self):
        from quodeq.api import security
        assert ww._WEBVIEW_UA_MARKER == security._WEBVIEW_UA_MARKER

    def test_user_agent_carries_marker(self):
        assert ww._WEBVIEW_UA_MARKER in ww._webview_user_agent()
