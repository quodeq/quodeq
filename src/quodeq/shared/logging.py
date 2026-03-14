"""Colored logging helpers for the Quodeq application."""

from __future__ import annotations

import logging
import os
import sys


def _should_use_color(env: dict[str, str] | None = None) -> bool:
    """Determine whether ANSI color codes should be emitted.

    *env* overrides ``os.environ`` when provided, making the check
    testable without environment mutation.
    """
    environ = env if env is not None else os.environ
    return not environ.get("NO_COLOR") and environ.get("TERM") != "dumb"


_USE_COLOR = _should_use_color()

BLUE   = "\033[0;34m" if _USE_COLOR else ""
GREEN  = "\033[0;32m" if _USE_COLOR else ""
YELLOW = "\033[1;33m" if _USE_COLOR else ""
GREY   = "\033[0;90m" if _USE_COLOR else ""
RED    = "\033[0;31m" if _USE_COLOR else ""
NC     = "\033[0m"    if _USE_COLOR else ""

_LOG_SUCCESS = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(_LOG_SUCCESS, "SUCCESS")

_STYLES: dict = {
    logging.DEBUG: (GREY, "[DEBUG]"),
    logging.INFO: (BLUE, "[INFO]"),
    _LOG_SUCCESS: (GREEN, "[SUCCESS]"),
    logging.WARNING: (YELLOW, "[WARNING]"),
    logging.ERROR: (RED, "[ERROR]"),
}


class _ColorFormatter(logging.Formatter):
    """Format log records with ANSI color codes based on severity level."""

    def format(self, record: logging.LogRecord) -> str:
        color, prefix = _STYLES.get(record.levelno, (NC, f"[{record.levelname}]"))
        return f"{color}{prefix}{NC} {record.getMessage()}"


class _StderrHandler(logging.StreamHandler):
    """StreamHandler that always resolves sys.stderr at emit time (supports pytest capsys)."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        self.setFormatter(_ColorFormatter())

    @property  # type: ignore[override]
    def stream(self):
        """Return the current stderr stream (resolves dynamically for test capture)."""
        return sys.stderr

    @stream.setter
    def stream(self, _) -> None:
        """Ignore attempts to set the stream (always uses sys.stderr)."""
        pass


# Module-level logger configuration is intentional — standard Python convention.
# The "quodeq" logger is set up once at import time so all log_* helpers work immediately.
_logger = logging.getLogger("quodeq")
_logger.addHandler(_StderrHandler())
_logger.propagate = False
_logger.setLevel(logging.INFO)

def _apply_env_log_level(level: str | None = None) -> None:
    """Apply *level* (or LOG_LEVEL env var) to the logger. Injectable for testing."""
    env_level = (level or os.environ.get("LOG_LEVEL", "")).upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        _logger.setLevel(getattr(logging, env_level))


_apply_env_log_level()


def log_info(message: str) -> None:
    """Log an informational message."""
    _logger.info(message)


def log_success(message: str) -> None:
    """Log a success message."""
    _logger.log(_LOG_SUCCESS, message)


def log_warning(message: str) -> None:
    """Log a warning message."""
    _logger.warning(message)


def log_debug(message: str) -> None:
    """Log a debug message."""
    _logger.debug(message)


def log_error(message: str) -> None:
    """Log an error message."""
    _logger.error(message)
