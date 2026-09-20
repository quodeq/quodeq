"""configure_stdio_utf8() lets a process print non-ASCII under a non-UTF-8 console.

Simulates the Windows cp1252 console (and POSIX ``LANG=C``) by forcing a child
interpreter to start with an ASCII stdout, then verifies that calling
configure_stdio_utf8() makes non-ASCII output succeed instead of raising
UnicodeEncodeError.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys

from quodeq.shared.text_io import configure_stdio_utf8
import pytest

# The code under test sets PYTHONUTF8 / QUODEQ_WEBVIEW_TOKEN for the process;
# restore os.environ wholesale so the env-leak guard in tests/conftest.py stays green.
pytestmark = pytest.mark.usefixtures("restore_environ")


def test_non_ascii_print_survives_ascii_console(tmp_path) -> None:
    script = tmp_path / "print_unicode.py"
    script.write_text(
        "from quodeq.shared.text_io import configure_stdio_utf8\n"
        "configure_stdio_utf8()\n"
        "print('caf\\u00e9 \\u2713 \\U0001f600')\n",
        encoding="utf-8",
    )
    # Force the child to start with an ASCII stdout (no UTF-8 mode), the way a
    # legacy Windows console / LANG=C terminal behaves.
    env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
    result = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "café".encode("utf-8") in result.stdout


def test_configure_stdio_utf8_is_safe_and_sets_pythonutf8(monkeypatch) -> None:
    # Streams without a reconfigure() method (e.g. StringIO) must not crash.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    configure_stdio_utf8()
    assert os.environ.get("PYTHONUTF8") == "1"
