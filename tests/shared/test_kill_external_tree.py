"""Stopping a run someone else started must not signal its launcher's process group.

A ``quodeq evaluate`` run as a CI step shares the process group of the
self-hosted runner service that launched it (verified on the macOS runner:
Runner.Listener and runsvc.sh share one pgid). ``killpg`` on that group would
stop the runner itself. A child spawned here sits in pytest's own group, the
same situation: the kill must reach the child and its descendants and leave
this process alive.
"""
from __future__ import annotations

import signal
import subprocess
import sys
import time

import pytest

from quodeq.shared.process_kill import kill_external_tree

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")


def _alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def test_kills_the_run_and_spares_the_shared_group() -> None:
    child = subprocess.Popen(["sleep", "30"])
    try:
        kill_external_tree(child.pid, signal.SIGTERM)
        assert child.wait(timeout=5) == -signal.SIGTERM
    finally:
        if _alive(child):
            child.kill()


def test_reaches_the_run_descendants() -> None:
    parent = subprocess.Popen(["sh", "-c", "sleep 30 & echo $!; wait"], stdout=subprocess.PIPE, text=True)
    grandchild = int(parent.stdout.readline())
    try:
        kill_external_tree(parent.pid, signal.SIGTERM)
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and subprocess.run(["kill", "-0", str(grandchild)], capture_output=True).returncode == 0:
            time.sleep(0.05)
        assert subprocess.run(["kill", "-0", str(grandchild)], capture_output=True).returncode != 0
    finally:
        subprocess.run(["kill", "-9", str(grandchild)], capture_output=True)
        if _alive(parent):
            parent.kill()


def test_external_stop_uses_the_group_safe_kill() -> None:
    from quodeq.services.jobs import ProcessControl
    assert ProcessControl().kill_tree is kill_external_tree
