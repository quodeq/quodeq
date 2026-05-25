from pathlib import Path

from quodeq.dashboard import _api_spawn, runner
from quodeq.dashboard._api_health import ApiConfig
from quodeq.dashboard._api_spawn import spawn_action_api

from tests.conftest import DummyProcess

_TEST_PORT = 7863
_TEST_HOST = "127.0.0.1"
_TEST_DASHBOARD_PORT = 3000
_TEST_API_PORT = 9000


def test_spawn_action_api_sets_env(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env
        return DummyProcess()

    monkeypatch.setattr(_api_spawn.subprocess, "Popen", fake_popen)
    spawn_action_api(_TEST_PORT, tmp_path / "fake.pid", _TEST_HOST)
    assert captured["env"]["QUODEQ_ACTION_API_PORT"] == str(_TEST_PORT)


def test_spawn_action_api_sets_static_dist(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env
        return DummyProcess()

    dist_path = tmp_path / "dist"
    monkeypatch.setattr(_api_spawn.subprocess, "Popen", fake_popen)
    spawn_action_api(_TEST_PORT, tmp_path / "fake.pid", _TEST_HOST, ApiConfig(static_dist=dist_path))
    assert captured["env"]["QUODEQ_STATIC_DIST"] == str(dist_path)


def test_force_action_api_host_port(monkeypatch):
    captured = {}

    class FakeProcess:
        def poll(self):
            return 0  # already exited

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

    def fake_ensure(host, port, static_dist=None, evaluations_dir=None):
        captured["host"] = host
        captured["port"] = port
        return f"http://{host}:{port}", FakeProcess()

    monkeypatch.setattr(runner, "_ensure_action_api_forced", fake_ensure)
    monkeypatch.setattr(runner, "maybe_build_ui", lambda *_args, **_kwargs: Path("ui/web/dist"))
    monkeypatch.setattr(runner, "check_dashboard_dev_prereqs", lambda: None)
    monkeypatch.setattr(runner, "validate_paths", lambda *_args, **_kwargs: None)

    config = runner.DashboardConfig(
        server=runner.ServerConfig(
            port=_TEST_DASHBOARD_PORT,
            api_host="0.0.0.0",
            api_port=_TEST_API_PORT,
            api_forced=True,
        ),
        build=runner.BuildConfig(
            open_browser=False,
            no_build=True,
            reinstall=False,
        ),
        reports_dir=Path("reports"),
        static_dist=Path("ui/web/dist"),
        repo_root=Path("."),
        reports_defaulted=True,
    )

    runner.run_dashboard(config)
    assert captured == {"host": "0.0.0.0", "port": 9000}
