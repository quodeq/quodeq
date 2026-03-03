from pathlib import Path

import pytest

from codecompass.dashboard import runner
from codecompass.dashboard.runner import DashboardConfig, run_dashboard, validate_paths


def test_validate_paths_missing_reports(tmp_path: Path):
    cfg = DashboardConfig(
        port=4173,
        reports_dir=tmp_path / "missing",
        static_dist=tmp_path / "ui/web/dist",
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
    )
    with pytest.raises(FileNotFoundError):
        validate_paths(cfg)


class DummyProcess:
    def __init__(self):
        self._returncode = 0

    def wait(self):
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        pass


def test_run_dashboard_invokes_node(tmp_path: Path, monkeypatch):
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    server_modules = tmp_path / "ui/server/node_modules"
    server_modules.mkdir(parents=True)

    popen_calls = []

    def fake_popen(args, **kwargs):
        popen_calls.append(args)
        return DummyProcess()

    monkeypatch.setattr("codecompass.dashboard.runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "codecompass.dashboard.runner._ensure_action_api",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8001", None),
    )
    monkeypatch.setattr(
        "codecompass.dashboard.runner._kill_stale_action_api",
        lambda *_args, **_kwargs: None,
    )

    config = DashboardConfig(
        port=4173,
        reports_dir=tmp_path / "reports",
        static_dist=static_dist,
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
    )

    exit_code = run_dashboard(config)
    assert exit_code == 0
    assert popen_calls
    assert popen_calls[0][0] == "node"


def test_run_dashboard_creates_default_reports(tmp_path: Path, monkeypatch):
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    server_modules = tmp_path / "ui/server/node_modules"
    server_modules.mkdir(parents=True)

    def fake_popen(args, **kwargs):
        return DummyProcess()

    monkeypatch.setattr("codecompass.dashboard.runner.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "codecompass.dashboard.runner._ensure_action_api",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8001", None),
    )
    monkeypatch.setattr(
        "codecompass.dashboard.runner._kill_stale_action_api",
        lambda *_args, **_kwargs: None,
    )

    reports_dir = tmp_path / "reports"
    config = DashboardConfig(
        port=4173,
        reports_dir=reports_dir,
        static_dist=static_dist,
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
        reports_defaulted=True,
    )

    exit_code = run_dashboard(config)
    assert exit_code == 0
    assert reports_dir.exists()


def test_choose_ui_port_skips_taken(monkeypatch):
    monkeypatch.setattr(runner, "_is_port_open", lambda host, port: port == 4173)
    port = runner._choose_ui_port(4173)
    assert port == 4174


def test_run_dashboard_auto_picks_ui_port(monkeypatch, tmp_path):
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")
    (tmp_path / "ui/server/node_modules").mkdir(parents=True)

    monkeypatch.setattr(runner, "_ensure_action_api", lambda *_args, **_kwargs: ("http://127.0.0.1:8001", None))
    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_is_port_open", lambda host, port: port == 4173)
    monkeypatch.setattr(
        runner,
        "_start_ui_server",
        lambda *_args, **_kwargs: type("Dummy", (), {"wait": lambda self: 0, "poll": lambda self: 0, "terminate": lambda self: None})(),
    )

    config = DashboardConfig(
        port=4173,
        reports_dir=tmp_path / "reports",
        static_dist=static_dist,
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
        reports_defaulted=True,
    )

    exit_code = run_dashboard(config)
    assert exit_code == 0
    assert config.port == 4174


def test_validate_paths_missing_reports_custom_message(tmp_path: Path):
    cfg = DashboardConfig(
        port=4173,
        reports_dir=tmp_path / "missing",
        static_dist=tmp_path / "ui/web/dist",
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
        reports_defaulted=False,
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        validate_paths(cfg)
    message = str(excinfo.value)
    assert "Reports directory not found" in message
    assert "mkdir -p" in message
    assert "omit --evaluations" in message
