"""macOS menubar must expose a 'Check for Updates…' item wired to quodeq.update."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MACOS_ONLY = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="menubar uses rumps, which is darwin-only",
)


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


def _load_menubar():
    """Import menubar with rumps/_helpers/_dashboard stubbed (sibling pattern)."""
    for mod_name in ("rumps", "_helpers", "_dashboard"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    rumps_stub = sys.modules["rumps"]
    rumps_stub.App = _FakeApp
    rumps_stub.MenuItem = _FakeMenuItem
    rumps_stub.timer = lambda *a, **kw: (lambda f: f)
    rumps_stub.notification = MagicMock()

    helpers_stub = sys.modules["_helpers"]
    helpers_stub.find_commands = MagicMock(return_value={})
    helpers_stub.find_icon = MagicMock(return_value=None)
    helpers_stub.is_evaluating = MagicMock(return_value=False)
    helpers_stub.source_user_path = MagicMock()

    dashboard_stub = sys.modules["_dashboard"]
    dashboard_stub.build_dashboard_cmd = MagicMock()
    dashboard_stub.cleanup_stderr_log = MagicMock()
    dashboard_stub.DashboardCallbacks = MagicMock()
    dashboard_stub.DashboardState = MagicMock()
    dashboard_stub.find_pids_on_port = MagicMock()
    dashboard_stub.find_running_port = MagicMock()
    dashboard_stub.kill_port_processes = MagicMock()
    dashboard_stub.open_stderr_log = MagicMock()
    dashboard_stub.wait_for_dashboard = MagicMock()
    dashboard_stub._STDERR_READ_MAX = 4096
    dashboard_stub._ERROR_DISPLAY_MAX = 200

    macos_dir = str(Path(__file__).resolve().parents[2] / "packaging" / "macos")
    if macos_dir not in sys.path:
        sys.path.insert(0, macos_dir)

    if "menubar" in sys.modules:
        del sys.modules["menubar"]

    import menubar  # noqa: PLC0415
    return menubar


@_MACOS_ONLY
def test_menubar_has_update_item() -> None:
    menubar = _load_menubar()
    app = menubar.QuodeqApp()
    assert "Updates" in app._update_item.title
