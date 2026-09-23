"""The webview's diagnostic log file, opened once for the process.

The native-window code paths run inside AppKit callbacks where a raised
exception is swallowed by the ObjC runtime, so they trace to this file
instead. Falls back to stderr when the log cannot be opened.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _diag_path() -> Path:
    """The webview debug log's path under the user's quodeq run directory."""
    return Path.home() / ".quodeq" / "run" / "webview_debug.log"


try:
    _diag_path().parent.mkdir(parents=True, exist_ok=True)
    diag = _diag_path().open("a", encoding="utf-8")  # noqa: SIM115 — lives for the process
except OSError:
    diag = sys.stderr
