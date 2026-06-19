"""#341 — menubar._load_config must not raise ValueError on non-numeric env values."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _load_config_fn():
    """Import _load_config without triggering the rumps/module-level int() calls."""
    # Stub out rumps and the local helper modules so the import succeeds
    # on non-macOS and without the actual rumps package installed.
    for mod_name in ("rumps", "_helpers", "_dashboard"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    # Provide required names that menubar references at module level
    rumps_stub = sys.modules["rumps"]
    rumps_stub.App = MagicMock()
    rumps_stub.MenuItem = MagicMock()
    rumps_stub.timer = lambda *a, **kw: (lambda f: f)

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

    # Add the macos packaging dir to path so the import finds menubar.py
    macos_dir = str(Path(__file__).resolve().parents[2] / "packaging" / "macos")
    if macos_dir not in sys.path:
        sys.path.insert(0, macos_dir)

    # Force reimport if already cached (from a prior test run)
    if "menubar" in sys.modules:
        del sys.modules["menubar"]

    import menubar  # noqa: PLC0415
    return menubar._load_config


class TestLoadConfigNonNumericEnv:
    def setup_method(self):
        self._load_config = _load_config_fn()

    def test_non_numeric_port_falls_back_to_default(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORT": "not-a-number"})
        assert port == 7863  # default

    def test_non_numeric_ports_falls_back_to_default(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORTS": "abc,def,ghi"})
        # Should fall back — not raise ValueError
        assert isinstance(ports, tuple)

    def test_valid_numeric_env_still_works(self) -> None:
        port, ports = self._load_config(env={"QUODEQ_PORT": "8080", "QUODEQ_PORTS": "8080,8081"})
        assert port == 8080
        assert ports == (8080, 8081)
