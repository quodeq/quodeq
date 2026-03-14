"""Minimal HTTP client for JSON API communication."""

from __future__ import annotations

import ipaddress
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

from quodeq.ports.data_errors import AuthError, NotFoundError, ServerError

_logger = logging.getLogger(__name__)
_ALLOW_PRIVATE_URLS = os.environ.get("QUODEQ_ALLOW_PRIVATE_URLS") == "1"


def _is_private_address(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address."""
    # Check common private hostnames directly
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        pass
    # Hostname — resolve and check all addresses
    try:
        for family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, OSError):
        pass
    return False

_HTTP_TIMEOUT_S = int(os.environ.get("QUODEQ_HTTP_TIMEOUT", "10"))
_MAX_RETRIES = int(os.environ.get("QUODEQ_HTTP_MAX_RETRIES", "3"))
_RETRY_BASE_DELAY_S = float(os.environ.get("QUODEQ_HTTP_RETRY_DELAY", "0.5"))
_RETRY_JITTER_S = float(os.environ.get("QUODEQ_HTTP_RETRY_JITTER", "0.3"))
_CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("QUODEQ_CB_THRESHOLD", "5"))
_CIRCUIT_BREAKER_RESET_S = int(os.environ.get("QUODEQ_CB_RESET", "60"))


@dataclass(frozen=True)
class HttpResponse:
    """Immutable container for an HTTP status code and parsed JSON payload."""

    status: int
    data: dict


def check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes.

    Errors are raised with generic messages only.  Callers MUST NOT
    surface ``response.data`` to end users — it may contain upstream
    error details that should remain internal.
    """
    if response.status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise AuthError("Authentication error")
    if response.status == HTTPStatus.NOT_FOUND:
        raise NotFoundError("Not found")
    if response.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        raise ServerError("Server error")


class HttpClient:
    """Simple HTTP client that performs GET requests and returns parsed JSON.

    Includes retry with exponential backoff and a thread-safe circuit breaker
    that trips after repeated network failures.
    """

    def __init__(
        self,
        *,
        timeout: int | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
        retry_jitter: float | None = None,
        cb_threshold: int | None = None,
        cb_reset: int | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else _HTTP_TIMEOUT_S
        self._max_retries = max_retries if max_retries is not None else _MAX_RETRIES
        self._retry_base_delay = retry_base_delay if retry_base_delay is not None else _RETRY_BASE_DELAY_S
        self._retry_jitter = retry_jitter if retry_jitter is not None else _RETRY_JITTER_S
        self._cb_threshold = cb_threshold if cb_threshold is not None else _CIRCUIT_BREAKER_THRESHOLD
        self._cb_reset = cb_reset if cb_reset is not None else _CIRCUIT_BREAKER_RESET_S
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

    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Send a GET request with retry + circuit breaker and return parsed JSON."""
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must use http or https scheme: {url!r}")

        parsed = urlparse(url)
        if parsed.scheme == "http":
            _logger.warning("Cleartext HTTP request to %s — consider using https://", parsed.hostname)

        hostname = parsed.hostname or ""
        if _is_private_address(hostname) and not _ALLOW_PRIVATE_URLS:
            raise ValueError(
                f"Requests to private/internal addresses are blocked: {hostname!r}. "
                "Set QUODEQ_ALLOW_PRIVATE_URLS=1 to allow."
            )

        if self._is_circuit_open():
            return HttpResponse(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "circuit breaker open — too many recent failures"})

        last_response: HttpResponse | None = None
        for attempt in range(self._max_retries):
            result = self._attempt_get(url, headers)
            last_response = result
            if result.status < HTTPStatus.INTERNAL_SERVER_ERROR:
                self._record_success()
                return result
            # Retry on 5xx / network errors with exponential backoff + jitter
            if attempt < self._max_retries - 1:
                delay = self._retry_base_delay * (2 ** attempt) + random.uniform(0, self._retry_jitter)
                time.sleep(delay)

        self._record_failure()
        assert last_response is not None
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
                payload = json.loads(exc.read().decode("utf-8")) if exc.fp else {"error": "http error"}
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {"error": "http error"}
            return HttpResponse(exc.code, payload)
        except (URLError, socket.timeout, OSError):
            return HttpResponse(HTTPStatus.BAD_GATEWAY, {"error": "network error"})
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HttpResponse(HTTPStatus.BAD_GATEWAY, {"error": "invalid response"})
