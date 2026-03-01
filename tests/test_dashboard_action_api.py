from pathlib import Path

from codecompass.dashboard import runner
from codecompass.dashboard.runner import _choose_action_api_port


def test_choose_action_api_port_skips_taken(monkeypatch):
    monkeypatch.setattr(runner, "_is_port_open", lambda *_args, **_kwargs: False)
    port = _choose_action_api_port(start=8001, taken={8001, 8002})
    assert port == 8003


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
    assert captured["env"]["CODECOMPASS_ACTION_API_PORT"] == "8001"


def test_dashboard_sets_action_api_env(monkeypatch):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env

        class Dummy:
            def wait(self):
                return 0

        return Dummy()

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    config = runner.DashboardConfig(
        port=3000,
        reports_dir=Path("reports"),
        static_dist=Path("ui/web/dist"),
        repo_root=Path("."),
        open_browser=False,
        no_build=True,
        reinstall=False,
        reports_defaulted=True,
    )

    runner._start_ui_server(config, "http://127.0.0.1:8001")
    assert captured["env"]["CODECOMPASS_ACTION_API"] == "http://127.0.0.1:8001"


def test_force_action_api_host_port(monkeypatch):
    captured = {}

    def fake_ensure(host, port):
        captured["host"] = host
        captured["port"] = port
        return f"http://{host}:{port}", None

    def fake_start_ui_server(config, action_api_url):
        class Dummy:
            def wait(self):
                return 0

            def poll(self):
                return 0

            def terminate(self):
                pass

        return Dummy()

    monkeypatch.setattr(runner, "_ensure_action_api_forced", fake_ensure)
    monkeypatch.setattr(runner, "_start_ui_server", fake_start_ui_server)
    monkeypatch.setattr(runner, "_npm_install", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_npm_build", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "validate_paths", lambda *_args, **_kwargs: None)

    config = runner.DashboardConfig(
        port=3000,
        reports_dir=Path("reports"),
        static_dist=Path("ui/web/dist"),
        repo_root=Path("."),
        open_browser=False,
        no_build=True,
        reinstall=False,
        reports_defaulted=True,
        api_host="0.0.0.0",
        api_port=9000,
        api_forced=True,
    )

    runner.run_dashboard(config)
    assert captured == {"host": "0.0.0.0", "port": 9000}
