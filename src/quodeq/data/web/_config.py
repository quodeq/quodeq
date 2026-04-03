"""HTTP client configuration: constants, env-parsing helpers, and config dataclass."""

from __future__ import annotations

import os
from dataclasses import dataclass

_ENV_ALLOW_PLAINTEXT_HTTP = "QUODEQ_ALLOW_PLAINTEXT_HTTP"
_DEFAULT_HTTP_TIMEOUT = 10
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_DELAY = 0.5
_DEFAULT_RETRY_JITTER = 0.3
_DEFAULT_CB_THRESHOLD = 5
_DEFAULT_CB_RESET = 60
_BACKOFF_BASE = 2


def _safe_int(raw: str, default: int) -> int:
    """Parse *raw* as int, returning *default* on ValueError."""
    try:
        return int(raw)
    except ValueError:
        return default


def _safe_float(raw: str, default: float) -> float:
    """Parse *raw* as float, returning *default* on ValueError."""
    try:
        return float(raw)
    except ValueError:
        return default


def _allow_private_urls(override: bool | None = None) -> bool:
    """Return True if private/internal URL requests are allowed.

    *override* bypasses the env var for testing.
    """
    if override is not None:
        return override
    return os.environ.get("QUODEQ_ALLOW_PRIVATE_URLS") == "1"


def _http_timeout_s(env: dict[str, str] | None = None) -> int:
    """Return HTTP timeout in seconds (reads env at call time). Must be > 0."""
    value = _safe_int((env or os.environ).get("QUODEQ_HTTP_TIMEOUT", str(_DEFAULT_HTTP_TIMEOUT)), _DEFAULT_HTTP_TIMEOUT)
    return max(1, value)


def _max_retries(env: dict[str, str] | None = None) -> int:
    """Return max HTTP retries (reads env at call time). Must be >= 1."""
    value = _safe_int((env or os.environ).get("QUODEQ_HTTP_MAX_RETRIES", str(_DEFAULT_MAX_RETRIES)), _DEFAULT_MAX_RETRIES)
    return max(1, value)


def _retry_base_delay_s(env: dict[str, str] | None = None) -> float:
    """Return retry base delay in seconds (reads env at call time). Must be >= 0."""
    value = _safe_float((env or os.environ).get("QUODEQ_HTTP_RETRY_DELAY", str(_DEFAULT_RETRY_BASE_DELAY)), _DEFAULT_RETRY_BASE_DELAY)
    return max(0.0, value)


def _retry_jitter_s(env: dict[str, str] | None = None) -> float:
    """Return retry jitter in seconds (reads env at call time). Must be >= 0."""
    value = _safe_float((env or os.environ).get("QUODEQ_HTTP_RETRY_JITTER", str(_DEFAULT_RETRY_JITTER)), _DEFAULT_RETRY_JITTER)
    return max(0.0, value)


def _circuit_breaker_threshold(env: dict[str, str] | None = None) -> int:
    """Return circuit breaker failure threshold (reads env at call time). Must be >= 1."""
    value = _safe_int((env or os.environ).get("QUODEQ_CB_THRESHOLD", str(_DEFAULT_CB_THRESHOLD)), _DEFAULT_CB_THRESHOLD)
    return max(1, value)


def _circuit_breaker_reset_s(env: dict[str, str] | None = None) -> int:
    """Return circuit breaker reset seconds (reads env at call time). Must be > 0."""
    value = _safe_int((env or os.environ).get("QUODEQ_CB_RESET", str(_DEFAULT_CB_RESET)), _DEFAULT_CB_RESET)
    return max(1, value)


@dataclass(frozen=True)
class HttpClientConfig:
    """Configuration parameters for HttpClient (grouping the six keyword-only settings)."""

    timeout: int | None = None
    max_retries: int | None = None
    retry_base_delay: float | None = None
    retry_jitter: float | None = None
    cb_threshold: int | None = None
    cb_reset: int | None = None
    allow_private_urls: bool | None = None
    allow_plaintext_http: bool | None = None
