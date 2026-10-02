"""run_git_streaming: the deadline and callback failures never leak processes."""
from __future__ import annotations

import os
import stat
import sys
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


def test_grandchild_holding_stderr_cannot_hang_the_deadline(tmp_path, monkeypatch):
    _install(tmp_path, monkeypatch, _GRANDCHILD)
    seen: list[str] = []
    started = time.monotonic()
    result = run_git_streaming(["clone"], timeout=1, env=_ENV, on_line=seen.append)
    assert result == (False, "git command timed out")
    assert time.monotonic() - started < 4
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
