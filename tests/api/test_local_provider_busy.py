"""Unit tests for local_provider_busy — declared provider surface only."""

from __future__ import annotations

from flask import Flask

from quodeq.api._assistant_helpers import local_provider_busy


class _FakeProvider:
    def __init__(self, running: list[object]):
        self._running = running
        self.calls: list[dict] = []

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        self.calls.append({"limit": limit, "reports_dir": reports_dir, "states": states})
        return self._running


def _app(provider) -> Flask:
    app = Flask(__name__)
    if provider is not None:
        app.config["_provider"] = provider
    return app


class TestLocalProviderBusy:
    def test_true_when_a_running_evaluation_exists(self):
        provider = _FakeProvider([object()])
        with _app(provider).app_context():
            assert local_provider_busy("ollama") is True
        assert provider.calls == [{"limit": 20, "reports_dir": None, "states": {"running"}}]

    def test_false_when_no_running_evaluations(self):
        provider = _FakeProvider([])
        with _app(provider).app_context():
            assert local_provider_busy("ollama") is False

    def test_false_when_provider_unset(self):
        with _app(None).app_context():
            assert local_provider_busy("ollama") is False

    def test_false_for_non_local_provider_without_touching_provider(self):
        provider = _FakeProvider([object()])
        with _app(provider).app_context():
            assert local_provider_busy("openrouter") is False
        assert provider.calls == []
