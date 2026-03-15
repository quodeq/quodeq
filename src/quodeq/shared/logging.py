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


def _use_color() -> bool:
    """Return whether color output is currently enabled (evaluated on each call)."""
    return _should_use_color()


def _color(code: str) -> str:
    """Return the ANSI *code* if color is enabled, else empty string."""
    return code if _use_color() else ""


_LOG_SUCCESS = 25  # between INFO(20) and WARNING(30)
logging.addLevelName(_LOG_SUCCESS, "SUCCESS")

_ANSI_GREY = "\033[0;90m"
_ANSI_BLUE = "\033[0;34m"
_ANSI_GREEN = "\033[0;32m"
_ANSI_YELLOW = "\033[1;33m"
_ANSI_RED = "\033[0;31m"
_NC = "\033[0m"

_STYLES: dict = {
    logging.DEBUG: (_ANSI_GREY, "[DEBUG]"),
    logging.INFO: (_ANSI_BLUE, "[INFO]"),
    _LOG_SUCCESS: (_ANSI_GREEN, "[SUCCESS]"),
    logging.WARNING: (_ANSI_YELLOW, "[WARNING]"),
    logging.ERROR: (_ANSI_RED, "[ERROR]"),
}


class _ColorFormatter(logging.Formatter):
    """Format log records with ANSI color codes based on severity level."""

    def format(self, record: logging.LogRecord) -> str:
        raw_color, prefix = _STYLES.get(record.levelno, ("", f"[{record.levelname}]"))
        if _use_color():
            return f"{raw_color}{prefix}{_NC} {record.getMessage()}"
        return f"{prefix} {record.getMessage()}"


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


# Module-level logger configuration is intentional -- standard Python convention.
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
