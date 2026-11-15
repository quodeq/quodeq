"""Cross-platform PID liveness probe (shared, cross-cutting).

Hoisted out of ``data/sqlite/index_sync.py`` so the cancel path
(``services/_external_jobs.py``) and the external-run PID reader
(``data/fs/report_parser/external_pid.py``) can both use it without a
cross-layer import.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.win_launch import program_argv


def is_pid_alive(pid: int) -> bool:
    """Return True if *pid* refers to a live process. POSIX + Windows.

    On POSIX, ``os.kill(pid, 0)`` is the canonical no-op probe.

    On Windows, ``os.kill(pid, 0)`` is *not* a probe — signal 0 is
    ``CTRL_C_EVENT``, and Python implements that via
    ``GenerateConsoleCtrlEvent(CTRL_C_EVENT, pid)``. For an invalid /
    non-existent pid the Win32 call can broadcast Ctrl+C to every
    process sharing the calling console, which on test runners means
    pytest itself receives KeyboardInterrupt mid-run. Use
    ``OpenProcess`` + ``GetExitCodeProcess`` instead, which are
    side-effect-free and tolerate dead PIDs cleanly.
    """
    if sys.platform == PLATFORM_WIN32:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid),
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


_PS_TIMEOUT_S = 5


def _on_windows() -> bool:
    return sys.platform == PLATFORM_WIN32


def _command_line_cmd(pid: int) -> list[str]:
    """The command that prints *pid*'s command line: ``ps`` on POSIX, CIM through PowerShell on Windows."""
    if _on_windows():
        query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", query]
    return ["ps", "-o", "command=", "-p", str(pid)]


def process_has_arg(pid: int, token: str) -> bool:
    """True when *pid* is alive and *token* is one of its whole argv tokens.

    Guards a PID read from a file before trusting or signalling it: the OS
    reuses PIDs, so a stale file can name any program. A whole token, not a
    substring: "quodeq" alone also sits in the interpreter's path
    (``.../quodeq/.venv/bin/python``) of every process run from that venv.
    A command line that cannot be read counts as not matching, on every
    platform: never signal a process we could not identify.
    """
    if not is_pid_alive(pid):
        return False
    try:
        out = subprocess.run(
            program_argv(_command_line_cmd(pid)),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_PS_TIMEOUT_S, check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return token in (out or "").split()


_START_SLACK_S = 2  # `ps lstart` has 1 s resolution; clocks and file mtimes can disagree slightly
_LSTART_FORMAT = "%a %b %d %H:%M:%S %Y"  # `ps -o lstart=` under LC_ALL=C


# pid -> start time. Fixed for as long as the process lives, and the dashboard
# asks every poll tick, so one `ps` per process, not per tick. An entry is
# dropped the moment its pid is seen dead (is_original_process), before the
# OS can hand the number to anyone else.
_START_TIMES: dict[int, float] = {}
_START_TIMES_MAX = 1024


def process_started_at(pid: int) -> float | None:
    """Epoch seconds *pid* started at, or None when unknown (dead, Windows, odd ``ps``)."""
    if sys.platform == PLATFORM_WIN32:
        return None
    if pid in _START_TIMES:
        return _START_TIMES[pid]
    started = _ps_start_time(pid)
    if started is not None:
        if len(_START_TIMES) >= _START_TIMES_MAX:
            _START_TIMES.clear()
        _START_TIMES[pid] = started
    return started


def _ps_start_time(pid: int) -> float | None:
    try:
        out = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_PS_TIMEOUT_S, check=False, env={**resolve_env(None), "LC_ALL": "C"},
        ).stdout.strip()
        return time.mktime(time.strptime(out, _LSTART_FORMAT)) if out else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def is_original_process(pid: int, recorded_at: float) -> bool:
    """True when *pid* is alive and is the process that recorded it at *recorded_at*.

    For a PID a process wrote about itself (a run's ``.pid``, ``status.json``):
    that process was already running when it wrote it, so a live *pid* that
    started *after* the record is a stranger the OS handed the number to once
    the original ended. Independent of how the process was launched, so an
    in-process ``quodeq review`` run counts like a ``quodeq evaluate`` one.
    Where the start time is unknown (Windows), liveness alone has to do.
    """
    if not is_pid_alive(pid):
        _START_TIMES.pop(pid, None)
        return False
    started = process_started_at(pid)
    return started is None or started <= recorded_at + _START_SLACK_S
