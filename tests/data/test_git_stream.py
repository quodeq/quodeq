"""run_git_streaming: lines reach the callback while git runs, with the guard."""
from __future__ import annotations

import os
import stat
import sys
import time

import pytest

from quodeq.data.fs import git_stream
from quodeq.data.fs.git_stream import run_git_streaming

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shebang fake git")

_FAKE = r'''#!/usr/bin/env python3
import sys, time
sys.stderr.write("Cloning into 'x'...\n"); sys.stderr.flush()
for p in (10, 45, 100):
    sys.stderr.write("Receiving objects: %3d%% (%d/100), 1.00 MiB\r" % (p, p)); sys.stderr.flush()
    time.sleep(0.05)
sys.stderr.write("\nResolving deltas: 100% (5/5), done.\n"); sys.stderr.flush()
sys.exit(int(sys.argv[-1] == "fail"))
'''


@pytest.fixture()
def fake_git(tmp_path, monkeypatch):
    script = tmp_path / "git"
    script.write_text(_FAKE)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(git_stream, "GIT_BIN", str(script))
    return script


def test_lines_arrive_incrementally_and_cr_splits(fake_git):
    seen: list[str] = []
    stamps: list[float] = []

    def on_line(line: str) -> None:
        seen.append(line)
        stamps.append(time.monotonic())

    ok, tail = run_git_streaming(["clone", "ok"], timeout=10, env={"PATH": os.environ["PATH"]}, on_line=on_line)
    finished = time.monotonic()
    assert ok is True
    receiving = [s for s in seen if s.startswith("Receiving")]
    assert receiving == [
        "Receiving objects:  10% (10/100), 1.00 MiB",
        "Receiving objects:  45% (45/100), 1.00 MiB",
        "Receiving objects: 100% (100/100), 1.00 MiB",
    ]
    assert tail.endswith("done.")
    # Streamed, not replayed at exit: the 10% line landed well before the end
    # and the 10% / 45% lines are about one 50 ms sleep apart.
    first, second = (stamps[seen.index(r)] for r in receiving[:2])
    assert finished - first > 0.08
    assert second > first


def test_nonzero_exit_is_false_with_tail(fake_git):
    ok, tail = run_git_streaming(["clone", "fail"], timeout=10, env={"PATH": os.environ["PATH"]}, on_line=lambda _l: None)
    assert ok is False and "Resolving deltas" in tail


def test_timeout_kills_and_reports(fake_git):
    fake_git.write_text(fake_git.read_text().replace("time.sleep(0.05)", "time.sleep(5)"))
    started = time.monotonic()
    ok, tail = run_git_streaming(["clone", "ok"], timeout=1, env={"PATH": os.environ["PATH"]}, on_line=lambda _l: None)
    assert ok is False and tail == "git command timed out"
    assert time.monotonic() - started < 4


def test_missing_binary_never_raises(monkeypatch):
    monkeypatch.setattr(git_stream, "GIT_BIN", "/nonexistent/git")
    assert run_git_streaming(["clone"], timeout=1, env={}, on_line=lambda _l: None) == (False, git_stream.GIT_MISSING)


def test_prompt_guard_and_stdin(fake_git, monkeypatch):
    captured = {}
    real_popen = git_stream.subprocess.Popen

    def spy(argv, **kwargs):
        captured.update(kwargs)
        return real_popen(argv, **kwargs)
    monkeypatch.setattr(git_stream.subprocess, "Popen", spy)
    run_git_streaming(["clone", "ok"], timeout=10, env={"PATH": os.environ["PATH"]}, on_line=lambda _l: None)
    assert captured["stdin"] is git_stream.subprocess.DEVNULL
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"
