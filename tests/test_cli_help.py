import subprocess
import sys


def test_cli_help_includes_dashboard():
    result = subprocess.run(
        [sys.executable, "-m", "codecompass.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dashboard" in result.stdout
    assert "evaluate" in result.stdout


def test_cli_dashboard_help():
    result = subprocess.run(
        [sys.executable, "-m", "codecompass.cli", "dashboard", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "codecompass dashboard" in result.stdout


def test_cli_dashboard_passes_subcommand_args(monkeypatch):
    captured = {}

    def fake_dashboard_main(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("codecompass.cli.dashboard_main", fake_dashboard_main)

    result = __import__("codecompass.cli", fromlist=["main"]).main(["dashboard"])

    assert result == 0
    assert captured["argv"] == []


def test_cli_evaluate_single_repo_defaults_discipline(monkeypatch):
    captured = {}

    def fake_run_evaluate(config):
        captured["config"] = config
        return 0

    monkeypatch.setattr("codecompass.cli.run_evaluate", fake_run_evaluate)

    result = __import__("codecompass.cli", fromlist=["main"]).main(["evaluate", "/repo/path"])

    assert result == 0
    assert captured["config"].repo == "/repo/path"
    assert captured["config"].discipline is None
