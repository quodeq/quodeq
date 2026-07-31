"""Low-level I/O helpers with centralized encoding.

``TEXT_ENCODING``, ``open_text`` and ``read_json`` moved inward to
``core/utils/io.py`` (stdlib-only) so domain modules can use them; they are
re-exported here for the rest of the codebase.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from quodeq.core.utils.io import (  # noqa: F401 — re-exported API
    TEXT_ENCODING,
    open_text,
    read_json,
)


def read_text(path: Path, *, errors: str = "strict") -> str:
    """Read a text file with the standard encoding."""
    return path.read_text(encoding=TEXT_ENCODING, errors=errors)


def write_text(path: Path, content: str) -> None:
    """Write a text file with the standard encoding."""
    path.write_text(content, encoding=TEXT_ENCODING)


def configure_stdio_utf8() -> None:
    """Ensure this process (and spawned Python children) use UTF-8 for console I/O.

    On Windows the console defaults to the active code page (e.g. cp1252), and a
    bare ``LANG=C`` locale does the same on POSIX; printing non-ASCII text (file
    paths, finding messages) then raises ``UnicodeEncodeError``. This reconfigures
    stdout/stderr to UTF-8 for the current process and defaults ``PYTHONUTF8=1`` so
    spawned Python children start in UTF-8 mode too. Call once at process entry; it
    is safe and idempotent, and no-ops on streams that cannot be reconfigured.
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
