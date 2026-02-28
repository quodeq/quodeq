import subprocess
import sys


def test_configure_subcommand_help():
    result = subprocess.run(
        [sys.executable, "-m", "codecompass.cli", "configure", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--ai-cli" in result.stdout


def test_configure_help_mentions_core_options():
    result = subprocess.run(
        [sys.executable, "-m", "codecompass.cli", "configure", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--generate-maps" in result.stdout
    assert "--add-discipline" in result.stdout
