"""Low-level I/O helpers with centralized encoding."""
from __future__ import annotations

from pathlib import Path
from typing import IO

TEXT_ENCODING = "utf-8"
"""Standard text encoding used across the codebase for file I/O."""


def read_text(path: Path, *, errors: str = "strict") -> str:
    """Read a text file with the standard encoding."""
    return path.read_text(encoding=TEXT_ENCODING, errors=errors)


def write_text(path: Path, content: str) -> None:
    """Write a text file with the standard encoding."""
    path.write_text(content, encoding=TEXT_ENCODING)


def open_text(path: str | Path, mode: str = "r") -> IO[str]:
    """Open a text file with the standard encoding. Use as a context manager."""
    return open(path, mode, encoding=TEXT_ENCODING)
