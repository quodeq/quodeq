"""A stand-in for ``shutil.which`` that searches the way it does on Windows.

For a command without a directory part Windows looks in the current
directory before PATH. Tests hand this to the launch helpers (or patch it
over ``shutil.which``) so a helper that passes a bare name on fails.
"""
from __future__ import annotations

import os

_PATHEXT = ("", ".exe", ".cmd", ".bat")


def windows_which(cmd: str, mode: int = os.F_OK | os.X_OK, path: str | None = None) -> str | None:
    """shutil.which as it searches on Windows: the current directory first."""
    dirname, name = os.path.split(cmd)
    if dirname:
        dirs = [dirname]
    else:
        dirs = [os.curdir, *(path if path is not None else os.environ.get("PATH", "")).split(os.pathsep)]
    for directory in dirs:
        for ext in _PATHEXT:
            candidate = os.path.join(directory, name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None
