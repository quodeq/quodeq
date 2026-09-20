"""Cross-platform 'kill the whole process tree' helper (shared, cross-cutting).

Hoisted out of assistant/adapters/_cli.py so the terminal layer can reuse it
without a cross-layer import. See tests/test_no_unguarded_posix.py: the POSIX
os.killpg call is allowlisted for this path.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from typing import Any

_logger = logging.getLogger(__name__)

_TERMINATE_TIMEOUT_S = 10
_KILL_WAIT_TIMEOUT_S = 5


def kill_tree(pid: int, sig: int = signal.SIGTERM) -> None:
    """Kill a process and all its children, cross-platform."""
    if sys.platform == "win32":
        # taskkill /T kills the entire process tree
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=_TERMINATE_TIMEOUT_S,
        )
    else:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, OSError) as exc:
                _logger.debug("process %s already gone: %s", pid, exc)


def terminate_process(process: subprocess.Popen) -> None:
    """Kill the process and its entire process tree to prevent orphans."""
    kill_tree(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=_TERMINATE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        kill_tree(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        try:
            process.wait(timeout=_KILL_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()


def _taskkill_tree(pid: int) -> bool:
    """Windows: kill the tree rooted at *pid* via taskkill. True when it succeeded."""
    try:
        result = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                capture_output=True, timeout=_TERMINATE_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError, TypeError) as exc:
        _logger.debug("taskkill failed for pid %s, falling back to proc.kill(): %s", pid, exc)
        return False
    # A non-zero exit (access denied, no such process, ...) means the tree
    # was NOT killed; the caller falls through to proc.kill().
    return result.returncode == 0


def _killpg_tree(pid: int) -> bool:
    """POSIX: SIGKILL the process group of *pid*. True when it succeeded."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, TypeError, AttributeError) as exc:
        _logger.debug("killpg failed for pid %s, falling back to proc.kill(): %s", pid, exc)
        return False
    return True


def kill_proc_tree(proc: Any) -> None:
    """Kill *proc* and its children. proc is a subprocess.Popen (or a test double
    exposing .pid/.kill()). Never raises for an already-dead or fake process."""
    pid = getattr(proc, "pid", None)
    # Only attempt a real process-group/tree kill when we have a real pid. A
    # test double or already-reaped proc (pid is None) must fall straight
    # through to proc.kill(): on Windows `taskkill /PID None` RUNS (exits
    # non-zero without raising) and would otherwise return before the fallback.
    if pid is not None:
        killed = _taskkill_tree(pid) if sys.platform == "win32" else _killpg_tree(pid)
        if killed:
            return
    try:
        proc.kill()
    except (ProcessLookupError, OSError, AttributeError) as exc:
        _logger.debug("process %s already gone: %s", pid, exc)
