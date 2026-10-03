"""The webview's diagnostic log file, opened once for the process.

The native-window code paths run inside AppKit callbacks where a raised
exception is swallowed by the ObjC runtime, so they trace to this file
instead. Falls back to stderr when the log cannot be opened.
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import TextIO


def _diag_path() -> Path:
    """The webview debug log's path under the user's quodeq run directory."""
    return Path.home() / ".quodeq" / "run" / "webview_debug.log"


@functools.cache
def diag_stream() -> TextIO:
    """Open (or reuse) the webview diagnostic log on the first trace."""
    try:
        _diag_path().parent.mkdir(parents=True, exist_ok=True)
        return _diag_path().open("a", encoding="utf-8")  # noqa: SIM115 — lives for the process
    except OSError:
        return sys.stderr


_DIAG_OLD_NAME = "diag"  # __getattr__ shim for the old module-level stream object


def __getattr__(name: str):
    if name == _DIAG_OLD_NAME:
        return diag_stream()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
