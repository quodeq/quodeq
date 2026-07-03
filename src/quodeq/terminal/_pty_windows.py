"""Windows ConPTY backend via pywinpty. Only imported on win32 (see backend.py)."""
from __future__ import annotations

import os
import shutil
import time

from winpty import PtyProcess  # type: ignore[import-untyped]

# When no output is buffered, pywinpty's read returns immediately with an empty
# string. Sleep briefly on empty so the reader thread doesn't hot-spin the CPU
# while an idle shell waits — mirrors the Unix backend's select() timeout, and
# keeps the read promptly stoppable (the reader loop re-checks its stop flag
# each cycle instead of parking).
_EMPTY_READ_SLEEP_S = 0.05


def resolve_shell(env: dict[str, str] | None = None) -> str:
    src = env if env is not None else os.environ
    for cand in ("pwsh", "powershell"):
        found = shutil.which(cand)
        if found:
            return found
    return src.get("COMSPEC", "cmd.exe")


class WindowsPty:
    def __init__(self, argv: list[str] | None = None, env: dict[str, str] | None = None):
        self._cmd = (argv[0] if argv else resolve_shell())
        self._env = env
        self._proc: PtyProcess | None = None

    def spawn(self, *, cwd: str, cols: int, rows: int) -> None:
        env = dict(self._env if self._env is not None else os.environ)
        for k in ("QUODEQ_API_KEY", "QUODEQ_ACTION_API_HOST", "QUODEQ_ACTION_API_PORT"):
            env.pop(k, None)
        self._proc = PtyProcess.spawn(self._cmd, cwd=cwd, env=env, dimensions=(rows, cols))

    def read(self, max_bytes: int = 65536) -> bytes:
        if self._proc is None or not self._proc.isalive():
            return b""
        try:
            data = self._proc.read(max_bytes)
        except EOFError:
            return b""
        if not data:
            time.sleep(_EMPTY_READ_SLEEP_S)
            return b""
        return data.encode("utf-8", "replace")

    def write(self, data: bytes) -> None:
        if self._proc is not None:
            self._proc.write(data.decode("utf-8", "replace"))

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is not None:
            self._proc.setwinsize(rows, cols)

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.isalive()

    def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate(force=True)
            except Exception:
                pass
