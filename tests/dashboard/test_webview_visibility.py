"""Native-window visibility events reaching the page."""
import json

from quodeq.dashboard._webview_window import dispatch_visibility, install_visibility_events
from quodeq.dashboard._webview_window_visibility import VISIBILITY_EVENT, visibility_js


class _FakeEvent:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self) -> None:
        for handler in self.handlers:
            handler()


class _FakeEvents:
    def __init__(self) -> None:
        self.minimized = _FakeEvent()
        self.restored = _FakeEvent()
        self.shown = _FakeEvent()


class _FakeWindow:
    def __init__(self, fail: bool = False) -> None:
        self.events = _FakeEvents()
        self.calls: list[str] = []
        self._fail = fail

    def evaluate_js(self, js: str) -> None:
        if self._fail:
            raise RuntimeError("window is gone")
        self.calls.append(js)


def _hidden_flags(window: _FakeWindow) -> list[bool]:
    return [json.dumps({"hidden": True}) in call for call in window.calls]


def test_snippet_carries_the_event_name_and_flag():
    assert VISIBILITY_EVENT in visibility_js(True)
    assert json.dumps({"hidden": True}) in visibility_js(True)
    assert json.dumps({"hidden": False}) in visibility_js(False)


def test_minimize_reports_hidden_and_restore_reports_visible():
    window = _FakeWindow()
    install_visibility_events(window)

    window.events.minimized.fire()
    window.events.restored.fire()

    assert _hidden_flags(window) == [True, False]


def test_show_reports_visible():
    window = _FakeWindow()
    install_visibility_events(window)

    window.events.shown.fire()

    assert _hidden_flags(window) == [False]


def test_a_dead_window_does_not_raise():
    dispatch_visibility(_FakeWindow(fail=True), True)
