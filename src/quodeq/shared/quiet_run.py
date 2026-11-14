"""Run a noisy child process quietly, with a spinner while it works.

``Spinner`` is also usable on its own for any wait a person watches.

npm and Vite print a line per package and per output chunk (100+ lines),
which is noise when the build works and the whole story when it doesn't.
The output goes to a temp file and is replayed to stderr only on failure.
On a terminal a spinner with the elapsed seconds shows the build is alive.
"""
from __future__ import annotations

import subprocess
import sys
import math
import tempfile
import time
from collections.abc import Mapping, Sequence
from typing import IO

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_TICK_S = 0.1  # spinner frame interval, also the child poll interval
_REAP_TIMEOUT_S = 5  # wait for the child to exit after kill()


def run_quiet(
    cmd: Sequence[str], *, label: str, cwd: str, timeout: float,
    env: Mapping[str, str] | None = None, stream: IO[str] | None = None,
) -> None:
    """Run *cmd*; raise ``CalledProcessError`` / ``TimeoutExpired`` like ``subprocess.run(check=True)``."""
    stream = stream or sys.stderr
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            _wait_with_spinner(proc, label, timeout, stream)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=_REAP_TIMEOUT_S)
            _replay(out, stream)
            raise
        if proc.returncode:
            _replay(out, stream)
            raise subprocess.CalledProcessError(proc.returncode, list(cmd))


class Spinner:
    """A one-line ``⠋ label 12s`` spinner, drawn only when *stream* is a terminal.

    Use as a context manager; the line is cleared on exit. ``animating`` is
    False off a terminal, so callers can fall back to plain log lines.
    It is also False when there is no stream at all: a windowed Windows exe
    has ``sys.stderr`` set to None.
    """

    def __init__(self, label: str, stream: IO[str] | None = None) -> None:
        self.label = label
        self._stream = stream or sys.stderr
        self.animating = self._stream is not None and self._stream.isatty()
        self._started = time.monotonic()
        self._frame = 0

    @property
    def elapsed(self) -> float:
        """Seconds since the spinner was created."""
        return time.monotonic() - self._started

    def tick(self) -> None:
        """Draw the next frame (a no-op off a terminal)."""
        if not self.animating:
            return
        frame = _FRAMES[self._frame % len(_FRAMES)]
        self._stream.write(f"\r{frame} {self.label} {self.elapsed:.0f}s")
        self._stream.flush()
        self._frame += 1

    def sleep(self, seconds: float) -> None:
        """Sleep *seconds*, redrawing every tick so the spinner never freezes."""
        steps = max(1, math.ceil(seconds / _TICK_S))
        for _ in range(steps):
            time.sleep(seconds / steps)
            self.tick()

    def __enter__(self) -> Spinner:
        return self

    def __exit__(self, *_exc: object) -> None:
        if self.animating:
            self._stream.write("\r\x1b[K")
            self._stream.flush()


def _wait_with_spinner(proc: subprocess.Popen, label: str, timeout: float, stream: IO[str] | None) -> None:
    with Spinner(label, stream) as spinner:
        while True:
            try:
                proc.wait(timeout=_TICK_S)
                return
            except subprocess.TimeoutExpired:
                if spinner.elapsed > timeout:
                    raise subprocess.TimeoutExpired(proc.args, timeout) from None
                spinner.tick()


def _replay(out: IO[bytes], stream: IO[str] | None) -> None:
    if stream is None:
        return
    out.seek(0)
    stream.write(out.read().decode(errors="replace"))
    stream.flush()
