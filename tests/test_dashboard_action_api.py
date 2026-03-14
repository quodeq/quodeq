from pathlib import Path

from quodeq.dashboard import _build, runner


def test_spawn_action_api_sets_env(monkeypatch):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env

        class Dummy:
            def poll(self):
                return None

            def terminate(self):
                return None

        return Dummy()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    runner._spawn_action_api(8001)
    assert captured["env"]["QUODEQ_ACTION_API_PORT"] == "8001"


def test_spawn_action_api_sets_static_dist(monkeypatch):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env

        class Dummy:
            def poll(self):
                return None

            def terminate(self):
                return None

        return Dummy()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    runner._spawn_action_api(8001, static_dist=Path("/tmp/dist"))
    assert captured["env"]["QUODEQ_STATIC_DIST"] == "/tmp/dist"


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
    monkeypatch.setattr(_build, "npm_build", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "validate_paths", lambda *_args, **_kwargs: None)

    config = runner.DashboardConfig(
        server=runner.ServerConfig(
            port=3000,
            api_host="0.0.0.0",
            api_port=9000,
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
