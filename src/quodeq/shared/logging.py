"""Colored logging helpers for the Quodeq application.

Formatting and handler classes live in ``_log_format``; this module
wires up the logger and exposes the ``log_*`` convenience functions.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum

from quodeq.shared.env_resolve import resolve_env
from quodeq.shared._log_format import (  # noqa: F401
    ColorFormatter as _ColorFormatter,
    StderrHandler as _StderrHandler,
    LOG_SUCCESS,
    color,
    should_use_color,
    use_color,
)

# Module-level logger configuration is intentional -- standard Python convention.
# The "quodeq" logger is set up once at import time so all log_* helpers work immediately.
_logger = logging.getLogger("quodeq")
_logger.addHandler(_StderrHandler())
_logger.propagate = False
_logger.setLevel(logging.INFO)


class _EnvLogLevel(StrEnum):
    """LOG_LEVEL values this module accepts (mirrors stdlib logging level names)."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def _apply_env_log_level(
    level: str | None = None, env: Mapping[str, str] | None = None,
) -> None:
    """Apply *level* (or LOG_LEVEL env var) to the logger. Injectable for testing."""
    env_level = (level or resolve_env(env).get("LOG_LEVEL", "")).upper()
    if env_level in _EnvLogLevel:
        _logger.setLevel(getattr(logging, env_level))


_apply_env_log_level()


def log_info(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log an informational message."""
    (logger or _logger).info(message)


def log_success(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a success message."""
    (logger or _logger).log(LOG_SUCCESS, message)


def log_warning(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a warning message."""
    (logger or _logger).warning(message)


def log_debug(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log a debug message."""
    (logger or _logger).debug(message)


def log_error(message: str, *, logger: logging.Logger | None = None) -> None:
    """Log an error message."""
    (logger or _logger).error(message)
