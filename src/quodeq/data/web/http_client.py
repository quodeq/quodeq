"""Minimal HTTP client for JSON API communication."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
import json
import socket
from urllib import request
from urllib.error import URLError
from urllib.parse import urlparse

from quodeq.data.ports.data_errors import AuthError, NotFoundError, ServerError
from quodeq.shared.ssrf import is_private_address as _is_private_address

_logger = logging.getLogger(__name__)


def _allow_private_urls(override: bool | None = None) -> bool:
    """Return True if private/internal URL requests are allowed.

    *override* bypasses the env var for testing.
    """
    if override is not None:
        return override
    return os.environ.get("QUODEQ_ALLOW_PRIVATE_URLS") == "1"

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
class HttpResponse:
    """Immutable container for an HTTP status code and parsed JSON payload."""

    status: int
    data: dict


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


def check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes.

    Errors are raised with generic messages only.  Callers MUST NOT
    surface ``response.data`` to end users — it may contain upstream
    error details that should remain internal.
    """
    if response.status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise AuthError("Authentication error — verify your API key is valid and not expired")
    if response.status == HTTPStatus.NOT_FOUND:
        raise NotFoundError("Resource not found — verify the URL and that the resource exists")
    if response.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        raise ServerError("Server error")


class HttpClient:
    """Simple HTTP client that performs GET requests and returns parsed JSON.

    Includes retry with exponential backoff and a thread-safe circuit breaker
    that trips after repeated network failures.
    """

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        cfg = config or HttpClientConfig()
        self._timeout = cfg.timeout if cfg.timeout is not None else _http_timeout_s()
        self._max_retries = cfg.max_retries if cfg.max_retries is not None else _max_retries()
        self._retry_base_delay = cfg.retry_base_delay if cfg.retry_base_delay is not None else _retry_base_delay_s()
        self._retry_jitter = cfg.retry_jitter if cfg.retry_jitter is not None else _retry_jitter_s()
        self._cb_threshold = cfg.cb_threshold if cfg.cb_threshold is not None else _circuit_breaker_threshold()
        self._cb_reset = cfg.cb_reset if cfg.cb_reset is not None else _circuit_breaker_reset_s()
        self._allow_private = cfg.allow_private_urls
        self._allow_plaintext_http = cfg.allow_plaintext_http
        self._lock = threading.Lock()
        self._failure_count = 0
        self._circuit_opened_at: float | None = None

    def _is_circuit_open(self) -> bool:
        with self._lock:
            if self._failure_count < self._cb_threshold:
                return False
            if self._circuit_opened_at and (time.monotonic() - self._circuit_opened_at) > self._cb_reset:
                self._failure_count = 0
                self._circuit_opened_at = None
                return False
            return True

    def _record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._circuit_opened_at = None

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._cb_threshold and self._circuit_opened_at is None:
                self._circuit_opened_at = time.monotonic()

    def _validate_url(self, url: str, env: dict[str, str] | None = None) -> None:
        """Validate URL scheme and check for private/plaintext restrictions.

        *env* overrides ``os.environ`` for testing (consistent with other
        functions in this module).

        .. note:: DNS rebinding caveat — hostname is resolved here but
           ``urlopen`` re-resolves independently.  For untrusted URLs in
           high-security contexts, pin the resolved IP or use a SOCKS proxy.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must use http or https scheme: {url!r}")

        parsed = urlparse(url)
        if parsed.scheme == "http":
            if self._allow_plaintext_http is not None:
                allow = self._allow_plaintext_http
            else:
                allow = (env or os.environ).get(_ENV_ALLOW_PLAINTEXT_HTTP) == "1"
            if not allow:
                raise ValueError(
                    f"Cleartext HTTP to {parsed.hostname!r} is blocked — credentials would be "
                    "transmitted unencrypted. Use https:// or set QUODEQ_ALLOW_PLAINTEXT_HTTP=1."
                )

        hostname = parsed.hostname or ""
        if _is_private_address(hostname) and not _allow_private_urls(self._allow_private):
            raise ValueError(
                f"Requests to private/internal addresses are blocked: {hostname!r}. "
                "Set QUODEQ_ALLOW_PRIVATE_URLS=1 to allow."
            )

    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Send a GET request with retry + circuit breaker and return parsed JSON."""
        self._validate_url(url)

        if self._is_circuit_open():
            return HttpResponse(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "circuit breaker open — too many recent failures", "code": "CIRCUIT_OPEN"},
            )

        last_response: HttpResponse | None = None
        for attempt in range(self._max_retries):
            result = self._attempt_get(url, headers)
            last_response = result
            if result.status < HTTPStatus.INTERNAL_SERVER_ERROR:
                self._record_success()
                return result
            # Retry on 5xx / network errors with exponential backoff + jitter
            if attempt < self._max_retries - 1:
                delay = self._retry_base_delay * (_BACKOFF_BASE ** attempt) + random.uniform(0, self._retry_jitter)
                time.sleep(delay)

        self._record_failure()
        if last_response is None:
            raise RuntimeError("No response received — max_retries may be 0")
        return last_response

    def _attempt_get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Perform a single GET attempt."""
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return HttpResponse(resp.status, payload)
        except request.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8")) if exc.fp else {"error": "http error", "code": "HTTP_ERROR"}
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {"error": "http error", "code": "HTTP_ERROR"}
            return HttpResponse(exc.code, payload)
        except (URLError, socket.timeout, OSError):
            return HttpResponse(HTTPStatus.BAD_GATEWAY, {"error": "network error", "code": "NETWORK_ERROR"})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HttpResponse(HTTPStatus.BAD_GATEWAY, {"error": "invalid response", "code": "INVALID_RESPONSE"})
