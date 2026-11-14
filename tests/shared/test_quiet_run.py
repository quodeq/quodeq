"""run_quiet hides a child's output on success and replays it on failure."""
from __future__ import annotations

import io
import subprocess
import sys

import pytest

from quodeq.shared.quiet_run import Spinner, run_quiet


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_success_hides_the_output(tmp_path):
    stream = io.StringIO()
    run_quiet([sys.executable, "-c", "print('vite chunk table')"], label="Building", cwd=str(tmp_path),
              timeout=30, stream=stream)
    assert stream.getvalue() == ""


def test_failure_replays_the_output(tmp_path):
    stream = io.StringIO()
    with pytest.raises(subprocess.CalledProcessError):
        run_quiet([sys.executable, "-c", "print('cannot resolve ./Foo'); raise SystemExit(1)"],
                  label="Building", cwd=str(tmp_path), timeout=30, stream=stream)
    assert "cannot resolve ./Foo" in stream.getvalue()


def test_timeout_kills_the_child_and_replays_the_output(tmp_path):
    stream = io.StringIO()
    script = "import time; print('still going', flush=True); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired):
        run_quiet([sys.executable, "-c", script], label="Building", cwd=str(tmp_path), timeout=1, stream=stream)
    assert "still going" in stream.getvalue()


def test_terminal_shows_a_spinner_and_clears_it(tmp_path):
    stream = _Tty()
    run_quiet([sys.executable, "-c", "import time; time.sleep(0.5)"], label="Building web UI",
              cwd=str(tmp_path), timeout=30, stream=stream)
    written = stream.getvalue()
    assert "Building web UI" in written
    assert written.endswith("\r\x1b[K")


def test_spinner_off_a_terminal_writes_nothing():
    stream = io.StringIO()
    with Spinner("Starting", stream) as spinner:
        spinner.sleep(0.05)
    assert not spinner.animating
    assert stream.getvalue() == ""


def test_spinner_sleep_keeps_drawing_through_a_long_wait():
    stream = _Tty()
    with Spinner("Starting the Action API", stream) as spinner:
        spinner.sleep(0.35)
    assert stream.getvalue().count("Starting the Action API") >= 3
    assert stream.getvalue().endswith("\r\x1b[K")


def test_spinner_without_any_stream_stays_silent(monkeypatch):
    # A windowed Windows exe (PyInstaller console=False) has sys.stderr None.
    monkeypatch.setattr(sys, "stderr", None)
    with Spinner("Starting") as spinner:
        spinner.tick()
    assert spinner.animating is False


def test_failure_without_any_stream_still_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    with pytest.raises(subprocess.CalledProcessError):
        run_quiet([sys.executable, "-c", "print('boom'); raise SystemExit(3)"],
                  label="build", cwd=str(tmp_path), timeout=30)
