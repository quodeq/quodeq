"""Minimal HTTP client for JSON API communication."""

from __future__ import annotations

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

from quodeq.ports.data_errors import AuthError, NotFoundError, ServerError

_HTTP_TIMEOUT_S = int(os.environ.get("QUODEQ_HTTP_TIMEOUT", "10"))
_MAX_RETRIES = int(os.environ.get("QUODEQ_HTTP_MAX_RETRIES", "3"))
_RETRY_BASE_DELAY_S = float(os.environ.get("QUODEQ_HTTP_RETRY_DELAY", "0.5"))
_RETRY_JITTER_S = 0.3
_CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("QUODEQ_CB_THRESHOLD", "5"))
_CIRCUIT_BREAKER_RESET_S = int(os.environ.get("QUODEQ_CB_RESET", "60"))


@dataclass(frozen=True)
class HttpResponse:
    """Immutable container for an HTTP status code and parsed JSON payload."""

    status: int
    data: dict


def check_response_status(response: HttpResponse) -> None:
    """Raise the appropriate error for non-success HTTP status codes."""
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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failure_count = 0
        self._circuit_opened_at: float | None = None

    def _is_circuit_open(self) -> bool:
        with self._lock:
            if self._failure_count < _CIRCUIT_BREAKER_THRESHOLD:
                return False
            if self._circuit_opened_at and (time.monotonic() - self._circuit_opened_at) > _CIRCUIT_BREAKER_RESET_S:
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
            if self._failure_count >= _CIRCUIT_BREAKER_THRESHOLD and self._circuit_opened_at is None:
                self._circuit_opened_at = time.monotonic()

    def get_json(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Send a GET request with retry + circuit breaker and return parsed JSON."""
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must use http or https scheme: {url!r}")
        if self._is_circuit_open():
            return HttpResponse(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "circuit breaker open — too many recent failures"})

        last_response: HttpResponse | None = None
        for attempt in range(_MAX_RETRIES):
            result = self._attempt_get(url, headers)
            last_response = result
            if result.status < HTTPStatus.INTERNAL_SERVER_ERROR:
                self._record_success()
                return result
            # Retry on 5xx / network errors with exponential backoff + jitter
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_BASE_DELAY_S * (2 ** attempt) + random.uniform(0, _RETRY_JITTER_S)
                time.sleep(delay)

        self._record_failure()
        assert last_response is not None
        return last_response

    def _attempt_get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        """Perform a single GET attempt."""
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
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
