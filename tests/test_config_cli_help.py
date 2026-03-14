import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def configure_help_output():
    """Run 'quodeq configure --help' once and return the result."""
    result = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "configure", "--help"],
        capture_output=True,
        text=True,
    )
    return result


def test_configure_subcommand_help(configure_help_output):
    assert configure_help_output.returncode == 0
    assert "--ai-cli" in configure_help_output.stdout


def test_configure_help_mentions_core_options(configure_help_output):
    assert "--generate-maps" in configure_help_output.stdout
    assert "--add-discipline" in configure_help_output.stdout
