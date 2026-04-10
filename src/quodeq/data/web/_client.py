"""HttpClient with retry, circuit breaker, and URL validation."""

from __future__ import annotations

import json
import logging
import os
import random
import socket
import threading
import time
from http import HTTPStatus
from urllib import request
from urllib.error import URLError
from urllib.parse import urlparse

from quodeq.shared.ssrf import is_private_address as _is_private_address

from quodeq.data.web._config import (
    _BACKOFF_BASE,
    _ENV_ALLOW_PLAINTEXT_HTTP,
    HttpClientConfig,
    _allow_private_urls,
    _circuit_breaker_reset_s,
    _circuit_breaker_threshold,
    _http_timeout_s,
    _max_retries,
    _retry_base_delay_s,
    _retry_jitter_s,
)
from quodeq.data.web._response import HttpResponse

_logger = logging.getLogger(__name__)


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
        if not _allow_private_urls(self._allow_private) and _is_private_address(hostname):
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
            import ssl as _ssl
            _ctx = _ssl.create_default_context()
            with request.urlopen(req, timeout=self._timeout, context=_ctx) as resp:
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
