"""POSIX PTY backend. Only imported on non-win32 (see backend.py), so the
POSIX-only stdlib imports are safe at module top level."""
from __future__ import annotations

import fcntl
import os
import struct
import subprocess
import sys
import termios

from quodeq.shared._process_kill import kill_proc_tree

_ALLOWED_SHELL_BASENAMES = frozenset({"zsh", "bash", "fish", "sh", "dash", "tcsh", "ksh"})


def resolve_shell(env: dict[str, str] | None = None) -> list[str]:
    """Return argv for a login+interactive shell, validating $SHELL against an
    allowlist (a crafted $SHELL is arbitrary-binary execution)."""
    src = env if env is not None else os.environ
    shell = src.get("SHELL", "")
    default = "/bin/zsh" if sys.platform == "darwin" else "/bin/bash"
    if not shell or not os.path.isabs(shell) or os.path.basename(shell) not in _ALLOWED_SHELL_BASENAMES:
        shell = default
    return [shell, "-il"]


class UnixPty:
    def __init__(self, argv: list[str] | None = None, env: dict[str, str] | None = None):
        self._argv = argv or resolve_shell()
        self._env = env
        self._proc: subprocess.Popen | None = None
        self._master_fd: int | None = None

    def spawn(self, *, cwd: str, cols: int, rows: int) -> None:
        master, slave = os.openpty()
        self._master_fd = master
        _set_winsize(master, cols, rows)
        env = dict(self._env if self._env is not None else os.environ)
        env["TERM"] = "xterm-256color"
        for k in ("QUODEQ_API_KEY", "QUODEQ_ACTION_API_HOST", "QUODEQ_ACTION_API_PORT"):
            env.pop(k, None)
        self._proc = subprocess.Popen(
            self._argv, cwd=cwd, env=env,
            stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, close_fds=True,
        )
        os.close(slave)  # child holds its own copy

    def read(self, max_bytes: int = 65536) -> bytes:
        if self._master_fd is None:
            return b""
        try:
            return os.read(self._master_fd, max_bytes)
        except OSError:
            return b""  # master closed / child exited

    def write(self, data: bytes) -> None:
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, data)
            except OSError:
                pass

    def resize(self, cols: int, rows: int) -> None:
        if self._master_fd is not None:
            _set_winsize(self._master_fd, cols, rows)

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def kill(self) -> None:
        if self._proc is not None:
            kill_proc_tree(self._proc)
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
