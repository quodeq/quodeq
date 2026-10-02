"""A git runner that streams stderr while the command runs.

`shared_repo_git.run_git` buffers output until exit, which is fine for
every command but clone and fetch: those print "--progress" lines the UI
wants to show as they happen. This runner keeps run_git's discipline
(prompt guard, closed stdin, explicit deadline, English locale, never
raises) and adds one thing: every stderr line, split on carriage returns
as well as newlines, is handed to *on_line* as soon as it arrives.

stderr is read in binary with ``os.read``, which returns as soon as any
bytes are available. A text-mode ``read(n)`` would block until *n* characters
or EOF and hold every progress line back until the end.

On POSIX git runs in its own session and the deadline kills the whole process
group: clone and fetch spawn helpers (ssh, git-remote-https, index-pack) that
inherit stderr, and a surviving helper (ssh blocked on a tty prompt) would keep
the pipe open and hang the read forever. On Windows only git itself is killed,
so a helper holding stderr open can delay the return there (see ``git_env``).

Never raises for anything git does. The one exception is *on_line* itself: if
the callback raises, git is killed and reaped first, then the error propagates.
"""
from __future__ import annotations

import codecs
import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from quodeq.data.fs.shared_repo_git import git_env
from quodeq.shared.constants import GIT_BIN
from quodeq.shared.git_errors import output_tail

_logger = logging.getLogger(__name__)
_TAIL_CHARS = 4096
_READ_BYTES = 4096
_REAP_SECONDS = 5
_TIMED_OUT = "git command timed out"
_FAILED_TO_RUN = "git command failed to run"
_SPLIT = ("\r", "\n")
_IS_WINDOWS = sys.platform == "win32"


def _kill_quietly(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError as exc:
        _logger.debug("git_stream: kill failed: %s", exc)


def _terminate(proc: subprocess.Popen) -> None:
    """Kill git and, on POSIX, every helper in its process group."""
    if _IS_WINDOWS:
        _kill_quietly(proc)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        _kill_quietly(proc)
    except OSError as exc:
        _logger.debug("git_stream: group kill failed: %s", exc)


def _reap(proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=_REAP_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _logger.warning("git_stream: could not reap git: %s", exc)


def _kill_on_deadline(proc: subprocess.Popen, fired: threading.Event) -> None:
    """Timer callback: flag the deadline first, then kill."""
    fired.set()
    _terminate(proc)


def _emit_chunks(buffer: str, on_line: Callable[[str], None]) -> str:
    """Hand every complete line in *buffer* to *on_line*; return the remainder."""
    while True:
        cut = min((i for i in (buffer.find(c) for c in _SPLIT) if i >= 0), default=-1)
        if cut < 0:
            return buffer
        line, buffer = buffer[:cut], buffer[cut + 1:]
        if line.strip():
            on_line(line)


def _pump(fd: int, on_line: Callable[[str], None]) -> str:
    """Read *fd* to EOF, emitting lines as they arrive; return the last 4 KiB."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    tail = ""
    buffer = ""
    while True:
        data = os.read(fd, _READ_BYTES)
        text = decoder.decode(data, final=not data)
        tail = (tail + text)[-_TAIL_CHARS:]
        buffer = _emit_chunks(buffer + text, on_line)
        if not data:
            break
    if buffer.strip():
        on_line(buffer)
    return tail


def run_git_streaming(
    args: list[str], *, cwd: Path | None = None, timeout: int,
    env: Mapping[str, str] | None = None, on_line: Callable[[str], None],
) -> tuple[bool, str]:
    """Run ``git *args``; stream stderr lines to *on_line*; ``(ok, tail)``."""
    try:
        proc = subprocess.Popen(
            [GIT_BIN, *args], cwd=str(cwd) if cwd else None, env=git_env(env),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            start_new_session=not _IS_WINDOWS,
        )
    except OSError:
        return False, _FAILED_TO_RUN
    if proc.stderr is None:
        _terminate(proc)
        _reap(proc)
        return False, _FAILED_TO_RUN
    fired = threading.Event()
    timer = threading.Timer(timeout, _kill_on_deadline, args=(proc, fired))
    timer.daemon = True
    timer.start()
    text = ""
    expired = False
    try:
        text = _pump(proc.stderr.fileno(), on_line)
        proc.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        expired = True
        _terminate(proc)
        _reap(proc)
    finally:
        timer.cancel()
        if proc.returncode is None:
            _terminate(proc)
            _reap(proc)
        proc.stderr.close()
    if (fired.is_set() or expired) and proc.returncode != 0:
        return False, _TIMED_OUT
    return proc.returncode == 0, output_tail(text)
