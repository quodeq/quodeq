"""quodeq.menubar.app — config parsing, menu wiring, quit semantics.

rumps is darwin-only and not installed on CI Linux, so it is stubbed in
sys.modules before the import (same pattern the retired
tests/packaging/test_menubar_*.py files used).
"""
from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch


class _FakeMenuItem:
    """Minimal rumps.MenuItem stand-in that keeps .title a real string."""

    def __init__(self, title="", callback=None):
        self.title = title
        self.callback = callback
        self._menuitem = MagicMock()

    def set_callback(self, cb):
        self.callback = cb


class _FakeApp:
    """Real base class so ``class QuodeqApp(rumps.App)`` instantiates for real.

    A bare ``MagicMock()`` as the base makes ``QuodeqApp()`` return a MagicMock
    (its ``__init__`` never runs), so we need a genuine class here. It accepts
    and ignores rumps.App's constructor args and tolerates attribute writes
    (e.g. ``self.icon``, ``self.template``, ``self.menu``).
    """

    def __init__(self, *args, **kwargs):
        pass


def _load_app_module():
    """Import quodeq.menubar.app with rumps stubbed."""
    rumps_stub = types.ModuleType("rumps")
    rumps_stub.App = _FakeApp
    rumps_stub.MenuItem = _FakeMenuItem
    rumps_stub.timer = lambda *a, **kw: (lambda f: f)
    rumps_stub.notification = MagicMock()
    rumps_stub.quit_application = MagicMock()
    sys.modules["rumps"] = rumps_stub

    sys.modules.pop("quodeq.menubar.app", None)
    module = importlib.import_module("quodeq.menubar.app")
    return module, rumps_stub


class TestLoadConfigNonNumericEnv:
    def setup_method(self):
        self._module, _ = _load_app_module()
        self._load_config = self._module._load_config

    def test_non_numeric_port_falls_back_to_default(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORT": "not-a-number"})
        assert port == 7863  # default

    def test_non_numeric_ports_falls_back_to_default(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORTS": "abc,def,ghi"})
        assert isinstance(ports, tuple)

    def test_valid_numeric_env_still_works(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORT": "8080", "QUODEQ_PORTS": "8080,8081"})
        assert port == 8080
        assert ports == (8080, 8081)


def _make_app():
    module, rumps_stub = _load_app_module()
    with patch.object(module, "_find_commands", return_value={}), \
         patch.object(module, "_find_icon", return_value=None):
        app = module.QuodeqApp()
    return module, rumps_stub, app


def test_menubar_has_update_item() -> None:
    _, _, app = _make_app()
    assert "Updates" in app._update_item.title


def test_menubar_has_quit_item() -> None:
    _, _, app = _make_app()
    assert app._quit_item.title == "Quit Quodeq Bar"


def test_quit_disables_preference_and_quits(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(tmp_path / "run"))
    module, rumps_stub, app = _make_app()

    from quodeq.menubar import state

    state.set_enabled(True)
    app._on_quit(None)
    assert state.is_enabled() is False
    rumps_stub.quit_application.assert_called_once()


def test_prereq_rows_exclude_quodeq() -> None:
    _, _, app = _make_app()
    assert set(app._prereq_items) == {"python3", "node", "claude"}


def test_start_uses_own_binary(monkeypatch) -> None:
    module, _, app = _make_app()
    popen = MagicMock()
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    stderr_log = MagicMock()
    assert app._launch_dashboard_process(stderr_log) is True
    cmd = popen.call_args.args[0]
    assert cmd == [sys.executable, "-m", "quodeq.dashboard", "--no-open", "--port", "7863"]
