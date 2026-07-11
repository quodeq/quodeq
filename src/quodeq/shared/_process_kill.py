"""Cross-platform 'kill the whole process tree' helper (shared, cross-cutting).

Hoisted out of assistant/adapters/_cli.py so the terminal layer can reuse it
without a cross-layer import. See tests/test_no_unguarded_posix.py: the POSIX
os.killpg call is allowlisted for this path.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any


def kill_proc_tree(proc: Any) -> None:
    """Kill *proc* and its children. proc is a subprocess.Popen (or a test double
    exposing .pid/.kill()). Never raises for an already-dead or fake process."""
    pid = getattr(proc, "pid", None)
    # Only attempt a real process-group/tree kill when we have a real pid. A
    # test double or already-reaped proc (pid is None) must fall straight
    # through to proc.kill(): on Windows `taskkill /PID None` RUNS (exits
    # non-zero without raising) and would otherwise return before the fallback.
    if pid is not None:
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10)
                return
            except (OSError, subprocess.SubprocessError, TypeError):
                pass
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError, TypeError, AttributeError):
                pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError, AttributeError):
        pass
