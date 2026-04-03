"""Minimal HTTP client for JSON API communication.

This module re-exports the public API from the internal sub-modules
so that existing ``from quodeq.data.web.http_client import …`` imports
continue to work unchanged.
"""

from quodeq.data.web._client import HttpClient
from quodeq.data.web._config import (
    HttpClientConfig,
    _allow_private_urls,
    _circuit_breaker_reset_s,
    _circuit_breaker_threshold,
    _http_timeout_s,
    _max_retries,
    _retry_base_delay_s,
    _retry_jitter_s,
    _safe_float,
    _safe_int,
)
from quodeq.data.web._response import HttpResponse, check_response_status

__all__ = [
    "HttpClient",
    "HttpClientConfig",
    "HttpResponse",
    "check_response_status",
    # Semi-private helpers re-exported for backward compatibility
    "_allow_private_urls",
    "_circuit_breaker_reset_s",
    "_circuit_breaker_threshold",
    "_http_timeout_s",
    "_max_retries",
    "_retry_base_delay_s",
    "_retry_jitter_s",
    "_safe_float",
    "_safe_int",
]
