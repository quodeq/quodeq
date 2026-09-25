"""quodeq.menubar.app — config parsing, menu wiring, quit semantics.

rumps is darwin-only and not installed on CI Linux, so it is stubbed in
sys.modules before the import (same pattern the retired
tests/packaging/test_menubar_*.py files used).
"""
from __future__ import annotations

import importlib
import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _restore_menubar_modules():
    """``_load_app_module`` stubs ``sys.modules["rumps"]`` and reimports
    ``quodeq.menubar.app`` against the stub. Restore both afterwards so a
    later test (in this file or another) does not inherit the stub or the
    module re-imported against it."""
    original_rumps = sys.modules.get("rumps")
    original_app = sys.modules.get("quodeq.menubar.app")
    yield
    if original_rumps is None:
        sys.modules.pop("rumps", None)
    else:
        sys.modules["rumps"] = original_rumps
    if original_app is None:
        sys.modules.pop("quodeq.menubar.app", None)
    else:
        sys.modules["quodeq.menubar.app"] = original_app


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
        _port, ports = self._load_config(env={"QUODEQ_PORTS": "abc,def,ghi"})
        assert ports == (7863, 7864, 7865, 7866, 7867, 7868, 7869)

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
    from quodeq.menubar import _app_lifecycle

    _, _, app = _make_app()
    popen = MagicMock()
    monkeypatch.setattr(_app_lifecycle.subprocess, "Popen", popen)
    stderr_log = MagicMock()
    assert app._launch_dashboard_process(stderr_log) is True
    cmd = popen.call_args.args[0]
    assert cmd == [sys.executable, "-m", "quodeq.dashboard", "--no-open", "--port", "7863"]


def _raising(message: str):
    """A stand-in that always raises, so the caller's fail-soft path runs."""
    def boom(*_args, **_kwargs):
        raise RuntimeError(message)
    return boom


def _assert_logs(monkeypatch, caplog, target: str, message: str, action, expected: str) -> None:
    """Patch *target* to raise, run *action*, and assert the debug line landed."""
    monkeypatch.setattr(target, _raising(message))
    with caplog.at_level(logging.DEBUG, logger="quodeq.menubar.app"):
        action()
    assert expected in caplog.text


def test_on_quit_logs_when_preference_set_fails(monkeypatch, caplog) -> None:
    _module, _, app = _make_app()
    _assert_logs(
        monkeypatch, caplog, "quodeq.menubar.state.set_enabled", "state write failed",
        lambda: app._on_quit(None), "could not disable menubar preference on quit",
    )


def test_on_check_updates_logs_when_check_fails(monkeypatch, caplog) -> None:
    _module, _, app = _make_app()
    _assert_logs(
        monkeypatch, caplog, "quodeq.update.checker.run_check", "update check failed",
        lambda: app._on_check_updates(None), "update check failed",
    )


def test_on_check_updates_logs_the_traceback_at_warning(monkeypatch, caplog) -> None:
    _module, _, app = _make_app()
    monkeypatch.setattr("quodeq.update.checker.run_check", _raising("boom"))
    with caplog.at_level(logging.WARNING, logger="quodeq.menubar.app"):
        app._on_check_updates(None)
    matching = [r for r in caplog.records if "failed" in r.getMessage()]
    assert matching, [r.getMessage() for r in caplog.records]
    assert any(r.exc_info for r in matching)
    assert "Traceback (most recent call last)" in caplog.text
    assert "RuntimeError: boom" in caplog.text


def test_poll_logs_when_update_status_check_fails(monkeypatch, caplog) -> None:
    _module, _, app = _make_app()
    _assert_logs(
        monkeypatch, caplog, "quodeq.update.checker.get_status", "status check failed",
        lambda: app._poll(None), "update availability check failed",
    )


def test_set_ui_state_running_enables_open_and_stop_only() -> None:
    _, _, app = _make_app()
    app._set_ui_state(running=True)
    assert app._open_item.callback == app._on_open
    assert app._start_item.callback is None
    assert app._stop_item.callback == app._on_stop
    app._open_item._menuitem.setEnabled_.assert_called_with(True)
    app._start_item._menuitem.setEnabled_.assert_called_with(False)
    app._stop_item._menuitem.setEnabled_.assert_called_with(True)


def test_set_ui_state_stopped_enables_start_only() -> None:
    _, _, app = _make_app()
    app._set_ui_state(running=False)
    assert app._open_item.callback is None
    assert app._start_item.callback == app._on_start
    assert app._stop_item.callback is None
    app._open_item._menuitem.setEnabled_.assert_called_with(False)
    app._start_item._menuitem.setEnabled_.assert_called_with(True)
    app._stop_item._menuitem.setEnabled_.assert_called_with(False)
