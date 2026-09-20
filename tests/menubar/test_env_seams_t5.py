"""The menu bar app takes its environment at construction, from main()."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _FakeApp:
    def __init__(self, *args, **kwargs):
        pass


def _load_app_module():
    """Import quodeq.menubar.app with rumps stubbed (mirrors tests/menubar/test_app.py)."""
    rumps_stub = types.ModuleType("rumps")
    rumps_stub.App = _FakeApp
    rumps_stub.MenuItem = MagicMock
    rumps_stub.timer = lambda *a, **kw: (lambda f: f)
    rumps_stub.notification = MagicMock()
    rumps_stub.quit_application = MagicMock()
    sys.modules["rumps"] = rumps_stub
    sys.modules.pop("quodeq.menubar.app", None)
    return importlib.import_module("quodeq.menubar.app")


@pytest.fixture
def app_module():
    return _load_app_module()


class TestLoadConfig:
    def test_uses_the_injected_value(self, app_module, monkeypatch):
        monkeypatch.setenv("QUODEQ_PORT", "9999")
        port, _ = app_module._load_config({"QUODEQ_PORT": "8080"})
        assert port == 8080

    def test_empty_injected_env_ignores_the_process(self, app_module, monkeypatch):
        monkeypatch.setenv("QUODEQ_PORT", "9999")
        monkeypatch.setenv("QUODEQ_PORTS", "1111")
        port, ports = app_module._load_config({})
        assert port == 7863
        assert ports[0] == 7863


class TestMenubarStatePathEmptyString:
    def test_empty_string_falls_back_to_the_default_path(self):
        from quodeq.menubar.state import get_menubar_state_path

        path = get_menubar_state_path({"QUODEQ_MENUBAR_STATE_PATH": "", "QUODEQ_DIR": ""})
        assert path == str(Path.home() / ".quodeq" / "menubar_state.json")


class TestQuodeqAppTakesEnv:
    def _app(self, module, env):
        module._find_commands = lambda *a, **kw: {}
        module._find_icon = lambda *a, **kw: None
        return module.QuodeqApp(env)

    def test_uses_the_injected_value(self, app_module, monkeypatch):
        monkeypatch.setenv("QUODEQ_PORT", "9999")
        assert self._app(app_module, {"QUODEQ_PORT": "8080"})._app_port == 8080

    def test_empty_injected_env_ignores_the_process(self, app_module, monkeypatch):
        monkeypatch.setenv("QUODEQ_PORT", "9999")
        assert self._app(app_module, {})._app_port == 7863


class TestMainThreadsEnvIntoThePathBootstrap:
    def test_passes_its_env_to_source_user_path(self, app_module, monkeypatch):
        seen: list[object] = []
        monkeypatch.setattr(app_module, "_source_user_path", lambda env=None: seen.append(env))
        monkeypatch.setattr(app_module._control, "is_running", lambda: True)
        injected = {"PATH": "/from-env"}
        app_module.main(injected)
        assert seen == [injected]

    def test_defaults_to_the_process_environment(self, app_module, monkeypatch):
        seen: list[object] = []
        monkeypatch.setattr(app_module, "_source_user_path", lambda env=None: seen.append(env))
        monkeypatch.setattr(app_module._control, "is_running", lambda: True)
        app_module.main()
        assert seen == [None]
