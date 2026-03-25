"""Thread-safe HTTP fetcher with circuit breaker and retry for knowledge refresh."""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from quodeq.shared.ssrf import is_private_address as _is_private_hostname

_logger = logging.getLogger(__name__)


class FetchClient:
    """Thread-safe HTTP fetcher with circuit breaker (trips after repeated failures)."""

    _CIRCUIT_THRESHOLD = 5
    _MAX_RETRIES = 2
    _RETRY_BACKOFF_S = 0.5

    def _record_success(self) -> None:
        """Reset the failure counter on a successful fetch."""
        with self._lock:
            self._failures = 0

    def _record_failure(self, exc: Exception) -> None:
        """Increment failures and log; trips circuit breaker at threshold."""
        with self._lock:
            self._failures += 1
            count = self._failures
        if count >= self._CIRCUIT_THRESHOLD:
            _logger.warning("Circuit breaker tripped (failure %d): %s", count, exc)
        else:
            _logger.debug("Fetch failure %d/%d: %s", count, self._CIRCUIT_THRESHOLD, exc)

    def _is_circuit_open(self) -> bool:
        """Return True if too many recent failures have tripped the circuit breaker."""
        with self._lock:
            return self._failures >= self._CIRCUIT_THRESHOLD

    def __init__(self, timeout_s: int = 15, allow_private: bool | None = None, env: dict[str, str] | None = None) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._timeout = timeout_s
        self._env = env
        if allow_private is not None:
            self._allow_private: bool = allow_private
        else:
            self._allow_private = (self._env or os.environ).get("QUODEQ_ALLOW_PRIVATE_URLS") == "1"

    def fetch(self, url: str, headers: dict | None = None) -> str | None:
        """Fetch *url* and return body text, or None on failure.

        Validates URL scheme (http/https only) and blocks requests to
        private/internal addresses unless QUODEQ_ALLOW_PRIVATE_URLS=1.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            _logger.warning("Blocked fetch with disallowed scheme: %s", parsed.scheme)
            return None
        hostname = parsed.hostname or ""
        if hostname and _is_private_hostname(hostname) and not self._allow_private:
            _logger.warning("Blocked fetch to private/internal address: %s", hostname)
            return None

        if self._is_circuit_open():
            return None

        last_exc: Exception | None = None
        for retry in range(self._MAX_RETRIES):
            try:
                if hostname and not self._allow_private and _is_private_hostname(hostname):
                    _logger.warning("Blocked fetch after DNS re-check: %s", hostname)
                    return None
                req = urllib.request.Request(url, headers=headers or {})
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    self._record_success()
                    return r.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_exc = exc
                if retry < self._MAX_RETRIES - 1:
                    _logger.debug("Fetch retry %d/%d after: %s", retry + 1, self._MAX_RETRIES, exc)
                    time.sleep(self._RETRY_BACKOFF_S * (retry + 1))

        if last_exc is not None:
            self._record_failure(last_exc)
        return None


# Module-level singleton with thread-safe lazy initialization.
# Global state is used here because the FetchClient carries mutable circuit-breaker
# counters that must be shared across all callers within a process.  Injectable
# via set_fetch_client() for testing.
_fetch_client_lock = threading.Lock()
_fetch_client_instance: FetchClient | None = None


def get_fetch_client(timeout_s: int = 15) -> FetchClient:
    """Return the module-level FetchClient singleton, creating it lazily.

    For tests, call ``set_fetch_client(mock)`` before the code under test.
    """
    global _fetch_client_instance
    with _fetch_client_lock:
        if _fetch_client_instance is None:
            _fetch_client_instance = FetchClient(timeout_s)
        return _fetch_client_instance


def set_fetch_client(client: FetchClient | None) -> None:
    """Replace or clear the module-level fetch client (e.g. for testing)."""
    global _fetch_client_instance
    with _fetch_client_lock:
        _fetch_client_instance = client


def fetch_url(url: str, headers: dict | None = None, *, client: FetchClient | None = None) -> str | None:
    """Fetch *url* using *client* or the module-level default."""
    return (client or get_fetch_client()).fetch(url, headers)
