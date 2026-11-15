"""Stop one process, also from a Windows app that has no console."""
from __future__ import annotations

import logging
import os
import signal
import sys
import time

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.process import is_pid_alive

_logger = logging.getLogger(__name__)

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
