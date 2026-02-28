import subprocess
import sys


def test_configure_dimensions_list():
    result = subprocess.run(
        [sys.executable, "-m", "codecompass.cli", "configure", "-d"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "aff" in result.stdout
    assert "affordability" in result.stdout
