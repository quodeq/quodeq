"""Color detection, ANSI formatter, and stderr handler for logging."""
from __future__ import annotations

import logging
import os
import sys

_LOG_SUCCESS = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(_LOG_SUCCESS, "SUCCESS")


def _should_use_color(env: dict[str, str] | None = None) -> bool:
    """Determine whether ANSI color codes should be emitted.

    *env* overrides ``os.environ`` when provided, making the check
    testable without environment mutation.
    """
    environ = env if env is not None else os.environ
    return not environ.get("NO_COLOR") and environ.get("TERM") != "dumb"


_USE_COLOR: bool = _should_use_color()


def _use_color() -> bool:
    """Return whether color output is enabled (cached at import time)."""
    return _USE_COLOR


def _color(code: str) -> str:
    """Return the ANSI *code* if color is enabled, else empty string."""
    return code if _USE_COLOR else ""


_ANSI_GREY = "\033[0;90m"
_ANSI_BLUE = "\033[0;34m"
_ANSI_GREEN = "\033[0;32m"
_ANSI_YELLOW = "\033[1;33m"
_ANSI_RED = "\033[0;31m"
_NC = "\033[0m"

_STYLES: dict[int, tuple[str, str]] = {
    logging.DEBUG: (_ANSI_GREY, "[DEBUG]"),
    logging.INFO: (_ANSI_BLUE, "[INFO]"),
    _LOG_SUCCESS: (_ANSI_GREEN, "[SUCCESS]"),
    logging.WARNING: (_ANSI_YELLOW, "[WARNING]"),
    logging.ERROR: (_ANSI_RED, "[ERROR]"),
}


class ColorFormatter(logging.Formatter):
    """Format log records with ANSI color codes based on severity level."""

    def format(self, record: logging.LogRecord) -> str:
        raw_color, prefix = _STYLES.get(record.levelno, ("", f"[{record.levelname}]"))
        if _use_color():
            return f"{raw_color}{prefix}{_NC} {record.getMessage()}"
        return f"{prefix} {record.getMessage()}"


class StderrHandler(logging.StreamHandler):
    """StreamHandler that always resolves sys.stderr at emit time (supports pytest capsys)."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        self.setFormatter(ColorFormatter())

    @property  # type: ignore[override]
    def stream(self):
        """Return the current stderr stream (resolves dynamically for test capture)."""
        return sys.stderr

    @stream.setter
    def stream(self, _) -> None:
        """Ignore attempts to set the stream (always uses sys.stderr)."""
        pass
