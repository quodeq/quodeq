import subprocess
import sys


def test_cli_help_includes_dashboard():
    result = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "dashboard" in result.stdout
    assert "evaluate" in result.stdout


def test_cli_dashboard_help():
    result = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "dashboard", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "quodeq dashboard" in result.stdout


def test_cli_dashboard_passes_subcommand_args(monkeypatch):
    captured = {}

    def fake_dashboard_main(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("quodeq.cli.dashboard_main", fake_dashboard_main)

    result = __import__("quodeq.cli", fromlist=["main"]).main(["dashboard"])

    assert result == 0
    assert captured["argv"] == []
