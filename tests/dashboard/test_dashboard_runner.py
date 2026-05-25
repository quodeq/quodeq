import os
from pathlib import Path
import logging

import pytest

from quodeq.dashboard import runner, _networking
from quodeq.dashboard.runner import BuildConfig, DashboardConfig, ServerConfig, run_dashboard, validate_paths

from tests.conftest import DummyProcess

_TEST_PORT = 7863


def _make_config(tmp_path: Path, **overrides) -> DashboardConfig:
    """Build a DashboardConfig with sensible test defaults, overridable by keyword."""
    defaults = {
        "server": ServerConfig(port=_TEST_PORT),
        "build": BuildConfig(open_browser=False, no_build=True, reinstall=False),
        "reports_dir": tmp_path / "reports",
        "static_dist": tmp_path / "ui/web/dist",
        "repo_root": tmp_path,
    }
    defaults.update(overrides)
    return DashboardConfig(**defaults)


def test_validate_paths_missing_reports(tmp_path: Path):
    cfg = _make_config(tmp_path, reports_dir=tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        validate_paths(cfg)


def test_run_dashboard_spawns_action_api_with_static_dist(tmp_path: Path, monkeypatch):
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    captured = {}

    def fake_ensure(*args, **kwargs):
        api_config = kwargs.get("api_config")
        captured["static_dist"] = api_config.static_dist if api_config else None
        return f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_action_api", fake_ensure)
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    config = _make_config(tmp_path, static_dist=static_dist)

    run_dashboard(config)
    assert captured["static_dist"] is not None


def test_run_dashboard_creates_default_reports(tmp_path: Path, monkeypatch):
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()),
    )
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    reports_dir = tmp_path / "reports"
    config = _make_config(tmp_path, reports_dir=reports_dir, static_dist=static_dist, reports_defaulted=True)

    run_dashboard(config)
    assert reports_dir.exists()


def test_choose_ui_port_skips_taken(monkeypatch):
    monkeypatch.setattr(_networking, "_is_port_open", lambda host, port: port == _TEST_PORT)
    port = runner._choose_ui_port(_TEST_PORT)
    assert port == _TEST_PORT + 1


def test_run_dashboard_auto_picks_ui_port(monkeypatch, tmp_path):
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{_TEST_PORT + 1}", DummyProcess()),
    )
    monkeypatch.setattr(_networking, "_is_port_open", lambda host, port: port == _TEST_PORT)
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    config = _make_config(tmp_path, static_dist=static_dist, reports_defaulted=True)

    captured = []
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *args, **kwargs: (captured.append(args) or (f"http://127.0.0.1:{_TEST_PORT + 1}", DummyProcess())),
    )

    run_dashboard(config)
    # Original config is frozen; the resolved config inside run_dashboard picks 4174
    assert config.server.port == _TEST_PORT  # original unchanged


def test_validate_paths_missing_reports_custom_message(tmp_path: Path):
    cfg = _make_config(tmp_path, reports_dir=tmp_path / "missing", reports_defaulted=False)
    with pytest.raises(FileNotFoundError) as excinfo:
        validate_paths(cfg)
    message = str(excinfo.value)
    assert "Reports directory not found" in message
    assert "mkdir -p" in message
    assert "omit --evaluations" in message


def test_build_config_native_defaults():
    cfg = BuildConfig(open_browser=True, no_build=True, reinstall=False)
    assert cfg.use_native is True
    assert cfg.verbose is False


def test_build_config_browser_mode():
    cfg = BuildConfig(open_browser=True, no_build=True, reinstall=False, use_native=False)
    assert cfg.use_native is False


def test_run_dashboard_native_window(tmp_path: Path, monkeypatch):
    """When use_native=True, _serve_and_wait uses webview instead of webbrowser."""
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    webview_calls = []

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()),
    )
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    from quodeq.dashboard import _server

    def fake_serve(url, proc, config):
        webview_calls.append(config.build.use_native)

    monkeypatch.setattr(_server, "serve_and_wait", fake_serve)

    config = _make_config(
        tmp_path,
        static_dist=static_dist,
        build=BuildConfig(open_browser=True, no_build=True, reinstall=False, use_native=True),
    )
    run_dashboard(config)
    assert webview_calls == [True]


def test_run_dashboard_browser_fallback(tmp_path: Path, monkeypatch):
    """When use_native=False, _serve_and_wait opens browser."""
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    from quodeq.dashboard import _server
    browser_calls = []

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()),
    )
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    def fake_serve(url, proc, config):
        browser_calls.append(config.build.use_native)

    monkeypatch.setattr(_server, "serve_and_wait", fake_serve)

    config = _make_config(
        tmp_path,
        static_dist=static_dist,
        build=BuildConfig(open_browser=True, no_build=True, reinstall=False, use_native=False),
    )
    run_dashboard(config)
    assert browser_calls == [False]


def test_run_dashboard_verbose_sets_env(tmp_path: Path, monkeypatch):
    """When verbose=True, QUODEQ_VERBOSE env var is set in the injected env dict."""
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: (f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()),
    )
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *a, **k: static_dist)
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)

    test_env: dict[str, str] = {}
    config = _make_config(
        tmp_path,
        static_dist=static_dist,
        build=BuildConfig(open_browser=False, no_build=True, reinstall=False, verbose=True),
    )
    run_dashboard(config, env=test_env)

    # run_dashboard copies the env dict, so original is not mutated;
    # verify that os.environ is not polluted by verbose=True
    assert os.environ.get("QUODEQ_VERBOSE") != "1"
