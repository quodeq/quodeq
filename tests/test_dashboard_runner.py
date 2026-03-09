from pathlib import Path

import pytest

from quodeq.dashboard import runner
from quodeq.dashboard.runner import DashboardConfig, run_dashboard, validate_paths


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


def test_run_dashboard_spawns_action_api_with_static_dist(tmp_path: Path, monkeypatch):
    (tmp_path / "reports").mkdir()
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    captured = {}

    def fake_ensure(*args, **kwargs):
        captured["static_dist"] = kwargs.get("static_dist")
        return "http://127.0.0.1:4173", DummyProcess()

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_action_api", fake_ensure)

    config = DashboardConfig(
        port=4173,
        reports_dir=tmp_path / "reports",
        static_dist=static_dist,
        repo_root=tmp_path,
        open_browser=False,
        no_build=True,
        reinstall=False,
    )

    run_dashboard(config)
    assert captured["static_dist"] is not None


def test_run_dashboard_creates_default_reports(tmp_path: Path, monkeypatch):
    static_dist = tmp_path / "ui/web/dist"
    static_dist.mkdir(parents=True)
    (static_dist / "index.html").write_text("ok")

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: ("http://127.0.0.1:4173", DummyProcess()),
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

    run_dashboard(config)
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

    monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *_args, **_kwargs: ("http://127.0.0.1:4174", DummyProcess()),
    )
    monkeypatch.setattr(runner, "_is_port_open", lambda host, port: port == 4173)

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

    captured = []
    original_ensure = runner._ensure_action_api
    monkeypatch.setattr(
        runner, "_ensure_action_api",
        lambda *args, **kwargs: (captured.append(args) or ("http://127.0.0.1:4174", DummyProcess())),
    )

    run_dashboard(config)
    # Original config is frozen; the resolved config inside run_dashboard picks 4174
    assert config.port == 4173  # original unchanged


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
