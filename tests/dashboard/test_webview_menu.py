"""The Help menu's navigate payload, and no menu bar on Windows and Linux."""
import inspect

from quodeq.dashboard import _webview_window as ww
from quodeq.dashboard._webview_window import NAVIGATE_HELP_JS


def test_navigate_payload_contract():
    assert "quodeq:navigate" in NAVIGATE_HELP_JS
    assert "detail: 'help'" in NAVIGATE_HELP_JS


def test_no_menu_bar_is_passed_to_the_webview():
    # pywebview draws a native menu bar on Windows and Linux for any menu it
    # is given. The sidebar's Help link is the only Help entry there.
    assert "menu=" not in inspect.getsource(ww._run_webview)
