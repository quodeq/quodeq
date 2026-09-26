"""Color detection, ANSI formatter, and stderr handler for logging."""
from __future__ import annotations

import functools
import logging
import sys
from collections.abc import Mapping

from quodeq.shared.env_resolve import resolve_env

LOG_SUCCESS = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(LOG_SUCCESS, "SUCCESS")

_TERM_DUMB = "dumb"  # TERM value meaning no color support


def should_use_color(env: Mapping[str, str] | None = None) -> bool:
    """Determine whether ANSI color codes should be emitted.

    *env* overrides ``os.environ`` when provided, making the check
    testable without environment mutation.
    """
    environ = resolve_env(env)
    return not environ.get("NO_COLOR") and environ.get("TERM") != _TERM_DUMB


@functools.cache
def use_color() -> bool:
    """Return whether color output is enabled (decided once, at first use)."""
    return should_use_color()


def color(code: str) -> str:
    """Return the ANSI *code* if color is enabled, else empty string."""
    return code if use_color() else ""


_USE_COLOR_OLD_NAME = "USE_COLOR"  # __getattr__ shim for the old module-level constant


def __getattr__(name: str):
    if name == _USE_COLOR_OLD_NAME:
        return use_color()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_ANSI_GREY = "\033[0;90m"
_ANSI_BLUE = "\033[0;34m"
_ANSI_GREEN = "\033[0;32m"
_ANSI_YELLOW = "\033[1;33m"
_ANSI_RED = "\033[0;31m"
_NC = "\033[0m"

_STYLES: dict[int, tuple[str, str]] = {
    logging.DEBUG: (_ANSI_GREY, "[DEBUG]"),
    logging.INFO: (_ANSI_BLUE, "[INFO]"),
    LOG_SUCCESS: (_ANSI_GREEN, "[SUCCESS]"),
    logging.WARNING: (_ANSI_YELLOW, "[WARNING]"),
    logging.ERROR: (_ANSI_RED, "[ERROR]"),
}


class ColorFormatter(logging.Formatter):
    """Format log records with ANSI color codes based on severity level."""

    def format(self, record: logging.LogRecord) -> str:
        raw_color, prefix = _STYLES.get(record.levelno, ("", f"[{record.levelname}]"))
        if use_color():
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
