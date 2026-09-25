"""Windows/Linux Help menu (non_macos_menu) and the shared navigate payload."""
import logging
import sys
import threading
import time

from quodeq.dashboard._webview_window import NAVIGATE_HELP_JS, non_macos_menu
from tests._timeouts import budget


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.called = threading.Event()

    def evaluate_js(self, js: str) -> None:
        self.calls.append(js)
        self.called.set()


def test_returns_none_on_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert non_macos_menu(_FakeWindow()) is None


def test_builds_single_help_menu_on_windows_and_linux(monkeypatch):
    import webview.menu as wm
    for platform in ("win32", "linux"):
        monkeypatch.setattr(sys, "platform", platform)
        menu = non_macos_menu(_FakeWindow())
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
    (help_menu,) = non_macos_menu(window)
    (action,) = help_menu.items
    action.function()
    assert window.called.wait(timeout=budget(5)), "evaluate_js was never called"
    assert window.calls == [NAVIGATE_HELP_JS]


def test_navigate_payload_contract():
    assert "quodeq:navigate" in NAVIGATE_HELP_JS
    assert "detail: 'help'" in NAVIGATE_HELP_JS


def _wait_for_records(caplog, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not caplog.records:
        time.sleep(0.01)


class _FailingWindow(_FakeWindow):
    def evaluate_js(self, js: str) -> None:
        super().evaluate_js(js)
        raise RuntimeError("boom")


def test_action_isolates_a_failing_evaluate_js_and_logs(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "win32")
    window = _FailingWindow()
    (help_menu,) = non_macos_menu(window)
    (action,) = help_menu.items
    with caplog.at_level(logging.WARNING, logger="quodeq.dashboard._webview_window_chrome"):
        action.function()
        assert window.called.wait(timeout=budget(5)), "evaluate_js was never called"
        _wait_for_records(caplog, budget(5))
    matching = [r for r in caplog.records if "failed" in r.getMessage()]
    assert matching, [r.getMessage() for r in caplog.records]
    assert any(r.exc_info for r in matching)
