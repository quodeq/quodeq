"""Windows/Linux Help menu (_non_macos_menu) and the shared navigate payload."""
import sys
import threading

from quodeq.dashboard._webview_window import _NAVIGATE_HELP_JS, _non_macos_menu


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.called = threading.Event()

    def evaluate_js(self, js: str) -> None:
        self.calls.append(js)
        self.called.set()


def test_returns_none_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _non_macos_menu(_FakeWindow()) is None


def test_builds_single_help_menu_on_windows_and_linux(monkeypatch):
    import webview.menu as wm
    for platform in ("win32", "linux"):
        monkeypatch.setattr(sys, "platform", platform)
        menu = _non_macos_menu(_FakeWindow())
        assert menu is not None and len(menu) == 1
        (help_menu,) = menu
        assert isinstance(help_menu, wm.Menu)
        assert help_menu.title == "Help"
        (action,) = help_menu.items
        assert isinstance(action, wm.MenuAction)
        assert action.title == "quodeq Help"


def test_action_dispatches_navigate_event(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    window = _FakeWindow()
    (help_menu,) = _non_macos_menu(window)
    (action,) = help_menu.items
    action.function()
    assert window.called.wait(timeout=5), "evaluate_js was never called"
    assert window.calls == [_NAVIGATE_HELP_JS]


def test_navigate_payload_contract():
    assert "quodeq:navigate" in _NAVIGATE_HELP_JS
    assert "detail: 'help'" in _NAVIGATE_HELP_JS
