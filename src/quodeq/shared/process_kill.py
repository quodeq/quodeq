"""Cross-platform 'kill the whole process tree' helper (shared, cross-cutting).

Used by services/, terminal/, and assistant/ so each layer can terminate
process trees without a cross-layer import. See tests/test_no_unguarded_posix.py:
the POSIX os.killpg call is allowlisted for this path.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from typing import Any

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.process import is_pid_alive

_logger = logging.getLogger(__name__)

_TERMINATE_TIMEOUT_S = 10
_KILL_WAIT_TIMEOUT_S = 5
# signal.CTRL_BREAK_EVENT only exists on Windows.
_CTRL_BREAK = getattr(signal, "CTRL_BREAK_EVENT", None)
_CTRL_BREAK_GRACE_S = 2.0  # how long a process gets to act on the request
_CTRL_BREAK_POLL_S = 0.1


def stop_process(pid: int) -> None:
    """End one process, leaving its children running.

    POSIX sends SIGTERM. Windows first asks with CTRL_BREAK, which lets the
    process shut down cleanly but only reaches one that shares our console.
    The packaged app has no console, so the request then fails or is never
    delivered; in both cases the process is terminated instead.
    """
    if sys.platform != PLATFORM_WIN32:
        os.kill(pid, signal.SIGTERM)
        return
    if _ctrl_break_ended(pid):
        return
    if is_pid_alive(pid):
        os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows


def _ctrl_break_ended(pid: int) -> bool:
    try:
        os.kill(pid, _CTRL_BREAK)
    except OSError as exc:
        _logger.debug("could not send CTRL_BREAK to %s: %s", pid, exc)
        return not is_pid_alive(pid)
    deadline = time.monotonic() + _CTRL_BREAK_GRACE_S
    while is_pid_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(_CTRL_BREAK_POLL_S)
    return True


def _run_taskkill(pid: int) -> subprocess.CompletedProcess[bytes]:
    """Windows: force-kill the tree rooted at *pid* (``taskkill /T``). Raises what ``subprocess.run`` raises."""
    return subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(pid)],
        capture_output=True, timeout=_TERMINATE_TIMEOUT_S,
    )


def kill_tree(pid: int, sig: int = signal.SIGTERM) -> None:
    """Kill a process and all its children, cross-platform."""
    if sys.platform == PLATFORM_WIN32:
        if not _taskkill_tree(pid):
            _logger.debug("taskkill did not kill tree %s", pid)
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
        result = _run_taskkill(pid)
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
        killed = _taskkill_tree(pid) if sys.platform == PLATFORM_WIN32 else _killpg_tree(pid)
        if killed:
            return
    try:
        proc.kill()
    except (ProcessLookupError, OSError, AttributeError) as exc:
        _logger.debug("process %s already gone: %s", pid, exc)


def _descendants(pid: int) -> list[int]:
    """POSIX: every live descendant of *pid*, from one ``ps`` snapshot; [] if ps fails."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, encoding="utf-8", timeout=_TERMINATE_TIMEOUT_S,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("ps failed listing descendants of %s: %s", pid, exc)
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        match line.split():
            case [child, parent] if child.isdigit() and parent.isdigit():
                children.setdefault(int(parent), []).append(int(child))
    found: list[int] = []
    stack = list(children.get(pid, []))
    while stack:
        child = stack.pop()
        found.append(child)
        stack.extend(children.get(child, []))
    return found


def kill_external_tree(pid: int, sig: int = signal.SIGTERM) -> None:
    """Kill a process someone else started, and its descendants, never its launcher.

    ``kill_tree`` signals the whole process group. That is only safe when
    *pid* leads its own group. A ``quodeq evaluate`` run as a CI step shares
    the group of the runner service that launched it, so a group kill would
    stop the runner. Then the process and its descendants are signalled one
    by one. Windows' ``taskkill /T`` already kills only the tree.
    """
    if sys.platform == PLATFORM_WIN32:
        kill_tree(pid, sig)
        return
    try:
        leads_group = os.getpgid(pid) == pid
    except (ProcessLookupError, OSError):
        leads_group = False
    if leads_group:
        kill_tree(pid, sig)
        return
    for target in [*_descendants(pid), pid]:
        try:
            os.kill(target, sig)
        except (ProcessLookupError, OSError) as exc:
            _logger.debug("process %s already gone: %s", target, exc)
