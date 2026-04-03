"""Colored logging helpers for the Quodeq application.

Formatting and handler classes live in ``_log_format``; this module
wires up the logger and exposes the ``log_*`` convenience functions.
"""
from __future__ import annotations

import logging
import os

from quodeq.shared._log_format import (  # noqa: F401
    ColorFormatter as _ColorFormatter,
    StderrHandler as _StderrHandler,
    _LOG_SUCCESS,
    _color,
    _should_use_color,
    _use_color,
    _USE_COLOR,
)

# Module-level logger configuration is intentional -- standard Python convention.
# The "quodeq" logger is set up once at import time so all log_* helpers work immediately.
_logger = logging.getLogger("quodeq")
_logger.addHandler(_StderrHandler())
_logger.propagate = False
_logger.setLevel(logging.INFO)


def _apply_env_log_level(level: str | None = None, env: dict | None = None) -> None:
    """Apply *level* (or LOG_LEVEL env var) to the logger. Injectable for testing."""
    env_level = (level or (env or os.environ).get("LOG_LEVEL", "")).upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        _logger.setLevel(getattr(logging, env_level))


_apply_env_log_level()


def log_info(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log an informational message."""
    (logger or _logger).info(message)


def log_success(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a success message."""
    (logger or _logger).log(_LOG_SUCCESS, message)


def log_warning(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a warning message."""
    (logger or _logger).warning(message)


def log_debug(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a debug message."""
    (logger or _logger).debug(message)


def log_error(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log an error message."""
    (logger or _logger).error(message)
