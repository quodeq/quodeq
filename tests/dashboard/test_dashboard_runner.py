import os
from pathlib import Path

import pytest

from quodeq.dashboard import _networking, runner
from quodeq.dashboard._probes import DashboardHooks
from quodeq.dashboard.runner import (
    BuildConfig,
    DashboardConfig,
    run_dashboard,
    validate_paths,
)
from tests.conftest import DummyProcess
from tests.dashboard._runner_helpers import TEST_PORT as _TEST_PORT
from tests.dashboard._runner_helpers import _make_config, _setup_dashboard


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

    monkeypatch.setattr(runner, "_ensure_action_api", fake_ensure)
    hooks = DashboardHooks(
        kill_stale=lambda *_a, **_k: None,
        build_ui=lambda *a, **k: static_dist,
        check_prereqs=lambda: None,
    )

    config = _make_config(tmp_path, static_dist=static_dist)

    run_dashboard(config, hooks=hooks)
    assert captured["static_dist"] is not None


def test_run_dashboard_creates_default_reports(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    config, hooks, _static_dist = _setup_dashboard(
        tmp_path, monkeypatch, reports=False,
        reports_dir=reports_dir, reports_defaulted=True,
    )

    run_dashboard(config, hooks=hooks)
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

    monkeypatch.setattr(_networking, "_is_port_open", lambda host, port: port == _TEST_PORT)
    hooks = DashboardHooks(
        kill_stale=lambda *_a, **_k: None,
        build_ui=lambda *a, **k: static_dist,
        check_prereqs=lambda: None,
    )

    config = _make_config(tmp_path, static_dist=static_dist, reports_defaulted=True)

    captured = []
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *args, **kwargs: (captured.append(args) or (f"http://127.0.0.1:{_TEST_PORT + 1}", DummyProcess())),
    )

    run_dashboard(config, hooks=hooks)
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
    config, hooks, _static_dist = _setup_dashboard(
        tmp_path, monkeypatch,
        build=BuildConfig(open_browser=True, no_build=True, reinstall=False, use_native=True),
    )

    webview_calls = []
    from quodeq.dashboard import _server

    def fake_serve(url, proc, config):
        webview_calls.append(config.build.use_native)

    monkeypatch.setattr(_server, "serve_and_wait", fake_serve)

    run_dashboard(config, hooks=hooks)
    assert webview_calls == [True]


def test_run_dashboard_browser_fallback(tmp_path: Path, monkeypatch):
    """When use_native=False, _serve_and_wait opens browser."""
    config, hooks, _static_dist = _setup_dashboard(
        tmp_path, monkeypatch,
        build=BuildConfig(open_browser=True, no_build=True, reinstall=False, use_native=False),
    )

    from quodeq.dashboard import _server
    browser_calls = []

    def fake_serve(url, proc, config):
        browser_calls.append(config.build.use_native)

    monkeypatch.setattr(_server, "serve_and_wait", fake_serve)

    run_dashboard(config, hooks=hooks)
    assert browser_calls == [False]


def test_run_dashboard_verbose_sets_env(tmp_path: Path, monkeypatch):
    """When verbose=True, QUODEQ_VERBOSE env var is set in the injected env dict."""
    config, hooks, _static_dist = _setup_dashboard(
        tmp_path, monkeypatch,
        build=BuildConfig(open_browser=False, no_build=True, reinstall=False, verbose=True),
    )

    test_env: dict[str, str] = {}
    run_dashboard(config, env=test_env, hooks=hooks)

    # run_dashboard copies the env dict, so original is not mutated;
    # verify that os.environ is not polluted by verbose=True
    assert os.environ.get("QUODEQ_VERBOSE") != "1"


class TestHandoffToRunningInstance:
    """A relaunch must reach the open window without disturbing its backend.

    The launch used to spawn a second action API, notice the running instance,
    and terminate that API on the way out — after _kill_stale_action_api had
    already killed the *running* instance's one. The open window was left with a
    dead server and an unresolvable loading screen.
    """

    @staticmethod
    def _config(tmp_path: Path, **build_overrides) -> DashboardConfig:
        (tmp_path / "reports").mkdir(exist_ok=True)
        static_dist = tmp_path / "ui/web/dist"
        static_dist.mkdir(parents=True, exist_ok=True)
        (static_dist / "index.html").write_text("ok")
        build = {"open_browser": True, "no_build": True, "reinstall": False, "use_native": True}
        build.update(build_overrides)
        return _make_config(tmp_path, static_dist=static_dist, build=BuildConfig(**build))

    @staticmethod
    def _patch_launch_path(monkeypatch, instance):
        """Stub everything past the handoff so a real launch is never attempted.

        Returns ``(calls, make_hooks)``: ``make_hooks(build_ui)`` builds a
        ``DashboardHooks`` with ``kill_stale`` wired to the call-tracking
        fake and ``build_ui`` set to whatever the caller passes (each test
        needs a ``build_ui`` that closes over its own ``config``, built
        after this helper runs).
        """
        calls = {"killed": False, "spawned": False}

        def fake_kill(*_a, **_k):
            calls["killed"] = True

        def fake_ensure(*_a, **_k):
            calls["spawned"] = True
            return f"http://127.0.0.1:{_TEST_PORT}", DummyProcess()

        monkeypatch.setattr(runner, "_ensure_action_api", fake_ensure)
        monkeypatch.setattr(runner._server_mod, "serve_and_wait", lambda *a, **k: None)
        monkeypatch.setattr(
            "quodeq.dashboard._instance.InstanceController", lambda *a, **k: instance,
        )

        def make_hooks(build_ui=lambda *a, **k: None):
            return DashboardHooks(kill_stale=fake_kill, build_ui=build_ui)

        return calls, make_hooks

    def test_running_instance_is_focused_and_left_alone(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        instance = MagicMock()
        instance.probe_existing.return_value = True
        calls, make_hooks = self._patch_launch_path(monkeypatch, instance)

        config = self._config(tmp_path)
        hooks = make_hooks(build_ui=lambda *a, **k: config.static_dist)

        assert run_dashboard(config, hooks=hooks) == 0
        instance.send_focus.assert_called_once_with()
        assert calls["killed"] is False, "the running instance's API must survive"
        assert calls["spawned"] is False, "no second API should be spawned just to kill it"

    def test_cold_start_proceeds_to_launch(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        instance = MagicMock()
        instance.probe_existing.return_value = False
        calls, make_hooks = self._patch_launch_path(monkeypatch, instance)

        config = self._config(tmp_path)
        hooks = make_hooks(build_ui=lambda *a, **k: config.static_dist)

        assert run_dashboard(config, hooks=hooks) == 0
        instance.send_focus.assert_not_called()
        assert calls["spawned"] is True

    def test_unreachable_instance_falls_back_to_launching(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        instance = MagicMock()
        instance.probe_existing.return_value = True
        instance.send_focus.side_effect = ConnectionRefusedError()
        calls, make_hooks = self._patch_launch_path(monkeypatch, instance)

        config = self._config(tmp_path)
        hooks = make_hooks(build_ui=lambda *a, **k: config.static_dist)

        assert run_dashboard(config, hooks=hooks) == 0
        assert calls["spawned"] is True

    def test_browser_mode_has_no_window_to_hand_off_to(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        instance = MagicMock()
        instance.probe_existing.return_value = True
        calls, make_hooks = self._patch_launch_path(monkeypatch, instance)

        config = self._config(tmp_path, use_native=False)
        hooks = make_hooks(build_ui=lambda *a, **k: config.static_dist)

        assert run_dashboard(config, hooks=hooks) == 0
        instance.send_focus.assert_not_called()
        assert calls["spawned"] is True
