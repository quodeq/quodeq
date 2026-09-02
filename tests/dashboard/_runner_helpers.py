"""Shared setup helpers for tests/dashboard/test_dashboard_runner.py.

Split out of test_dashboard_runner.py to shrink the repeated
static_dist/hooks/_ensure_action_api boilerplate each test needed.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.dashboard import runner
from quodeq.dashboard._probes import DashboardHooks
from quodeq.dashboard.runner import BuildConfig, DashboardConfig
from tests.conftest import DummyProcess

TEST_PORT = 7863


def _make_config(tmp_path: Path, **overrides) -> DashboardConfig:
    """Build a DashboardConfig with sensible test defaults, overridable by keyword."""
    defaults = {
        "server": runner.ServerConfig(port=TEST_PORT),
        "build": BuildConfig(open_browser=False, no_build=True, reinstall=False),
        "reports_dir": tmp_path / "reports",
        "static_dist": tmp_path / "ui/web/dist",
        "repo_root": tmp_path,
    }
    defaults.update(overrides)
    return DashboardConfig(**defaults)


def _setup_dashboard(
    tmp_path: Path, monkeypatch, *, reports: bool = True, **config_overrides,
) -> tuple[DashboardConfig, DashboardHooks, Path]:
    """Build a config + hooks + a spawned static_dist with the standard
    "spawn a fake action API" wiring every vanilla run_dashboard test needs.

    Returns ``(config, hooks, static_dist)``. Callers needing a custom
    ``_ensure_action_api`` or a non-default hook still patch/build those
    themselves; this only covers the common case.
    """
    if reports:
        (tmp_path / "reports").mkdir(exist_ok=True)
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True, exist_ok=True)
    (static_dist / "index.html").write_text("ok")

    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{TEST_PORT}", DummyProcess()),
    )
    hooks = DashboardHooks(
        kill_stale=lambda *_a, **_k: None,
        build_ui=lambda *a, **k: static_dist,
        check_prereqs=lambda: None,
    )
    config = _make_config(tmp_path, static_dist=static_dist, **config_overrides)
    return config, hooks, static_dist
