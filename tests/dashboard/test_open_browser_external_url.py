"""_WindowApi.open_browser: absolute web URLs must open as-is.

The update banner's "what's new" button passes the GitHub release URL
through this API. Prefixing it with the local dashboard base URL sends
the user to http://127.0.0.1:PORT/https://github.com/... — a 404.
"""
from unittest.mock import MagicMock, patch

from quodeq.dashboard import _webview_window as ww


def _bound_api(base_url: str = "http://127.0.0.1:7863") -> ww._WindowApi:
    api = ww._WindowApi()
    api.bind(MagicMock(), base_url=base_url)
    return api


class TestOpenBrowser:
    def test_absolute_https_url_opens_unprefixed(self):
        api = _bound_api()
        with patch.object(ww.webbrowser, "open") as opened:
            api.open_browser("https://github.com/quodeq/quodeq/releases/tag/v1.5.2")
        opened.assert_called_once_with("https://github.com/quodeq/quodeq/releases/tag/v1.5.2")

    def test_absolute_http_url_opens_unprefixed(self):
        api = _bound_api()
        with patch.object(ww.webbrowser, "open") as opened:
            api.open_browser("http://example.com/page")
        opened.assert_called_once_with("http://example.com/page")

    def test_relative_path_still_gets_base_url(self):
        api = _bound_api()
        with patch.object(ww.webbrowser, "open") as opened:
            api.open_browser("/help")
        opened.assert_called_once_with("http://127.0.0.1:7863/help")

    def test_default_path_opens_dashboard_root(self):
        api = _bound_api()
        with patch.object(ww.webbrowser, "open") as opened:
            api.open_browser()
        opened.assert_called_once_with("http://127.0.0.1:7863/")

    def test_non_web_scheme_is_not_treated_as_absolute(self):
        # javascript:/file: etc. keep the old prefixing behavior, which
        # renders them harmless relative paths on the local origin.
        api = _bound_api()
        with patch.object(ww.webbrowser, "open") as opened:
            api.open_browser("javascript:alert(1)")
        opened.assert_called_once_with("http://127.0.0.1:7863javascript:alert(1)")
