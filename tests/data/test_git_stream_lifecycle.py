"""run_git_streaming: the deadline and callback failures never leak processes."""
from __future__ import annotations

import os
import stat
import sys
import threading
import time

import pytest

from quodeq.data.fs import git_stream
from quodeq.data.fs.git_stream import run_git_streaming

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shebang fake git, POSIX groups")

_ENV = {"PATH": os.environ["PATH"]}

_GRANDCHILD = r'''#!/usr/bin/env python3
import subprocess, sys, time
c = subprocess.Popen(["sleep", "30"])
sys.stderr.write("child=%d\n" % c.pid); sys.stderr.flush()
time.sleep(30)
'''

_CHATTY = r'''#!/usr/bin/env python3
import os, sys, time
sys.stderr.write("pid=%d\n" % os.getpid()); sys.stderr.flush()
for i in range(3):
    sys.stderr.write("line %d\n" % i); sys.stderr.flush()
    time.sleep(0.05)
time.sleep(30)
'''


def _install(tmp_path, monkeypatch, body: str) -> None:
    script = tmp_path / "git"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(git_stream, "GIT_BIN", str(script))


def _gone(pid: int) -> bool:
    for _ in range(40):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _pid(seen: list[str], key: str) -> int:
    return int(next(s for s in seen if s.startswith(key + "=")).split("=")[1])


class _DeadlineOnCue(threading.Thread):
    """The deadline timer, fired by the test's cue instead of the clock."""

    def __init__(self, cue: threading.Event, function, args) -> None:
        super().__init__(daemon=True)
        self._cue, self._function, self._args = cue, function, args
        self._cancelled = False

    def run(self) -> None:
        self._cue.wait()
        if not self._cancelled:
            self._function(*self._args)

    def cancel(self) -> None:
        self._cancelled = True
        self._cue.set()


class _CuedThreading:
    """``threading`` as git_stream sees it, with the deadline timer on *cue*."""

    def __init__(self, cue: threading.Event) -> None:
        self._cue = cue

    def Timer(self, _interval, function, args):  # noqa: N802 - mirrors threading.Timer
        return _DeadlineOnCue(self._cue, function, args)

    def __getattr__(self, name: str):
        return getattr(threading, name)


def test_grandchild_holding_stderr_cannot_hang_the_deadline(tmp_path, monkeypatch):
    # The deadline fires once the grandchild is known to exist. On the clock
    # it could fire before a slow interpreter start had spawned it.
    _install(tmp_path, monkeypatch, _GRANDCHILD)
    seen: list[str] = []
    grandchild_up = threading.Event()
    deadline_at: list[float] = []

    def on_line(line: str) -> None:
        seen.append(line)
        if line.startswith("child="):
            deadline_at.append(time.monotonic())
            grandchild_up.set()

    monkeypatch.setattr(git_stream, "threading", _CuedThreading(grandchild_up))
    result = run_git_streaming(["clone"], timeout=1, env=_ENV, on_line=on_line)
    assert result == (False, "git command timed out")
    assert time.monotonic() - deadline_at[0] < 3
    assert _gone(_pid(seen, "child"))


def test_raising_callback_kills_and_reaps_git(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, _CHATTY)
    seen: list[str] = []

    def on_line(line: str) -> None:
        seen.append(line)
        if line == "line 0":
            raise ValueError("boom")

    with pytest.raises(ValueError):
        run_git_streaming(["clone"], timeout=20, env=_ENV, on_line=on_line)
    assert _gone(_pid(seen, "pid"))
