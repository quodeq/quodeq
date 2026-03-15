"""Thread-safe HTTP fetcher with circuit breaker for knowledge refresh."""
from __future__ import annotations

import threading
import urllib.error
import urllib.request


class FetchClient:
    """Thread-safe HTTP fetcher with circuit breaker (trips after repeated failures)."""

    _CIRCUIT_THRESHOLD = 5

    def __init__(self, timeout_s: int = 15) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._timeout = timeout_s

    def fetch(self, url: str, headers: dict | None = None) -> str | None:
        """Fetch *url* and return body text, or None on failure."""
        with self._lock:
            if self._failures >= self._CIRCUIT_THRESHOLD:
                return None
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                with self._lock:
                    self._failures = 0
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, ValueError):
            with self._lock:
                self._failures += 1
            return None


_fetch_client_lock = threading.Lock()
_fetch_client_instance: FetchClient | None = None


def get_fetch_client(timeout_s: int = 15) -> FetchClient:
    """Return the module-level FetchClient, creating it lazily on first use."""
    global _fetch_client_instance
    with _fetch_client_lock:
        if _fetch_client_instance is None:
            _fetch_client_instance = FetchClient(timeout_s)
        return _fetch_client_instance


def set_fetch_client(client: FetchClient) -> None:
    """Replace the module-level fetch client (e.g. for testing)."""
    global _fetch_client_instance
    with _fetch_client_lock:
        _fetch_client_instance = client


def fetch_url(url: str, headers: dict | None = None, *, client: FetchClient | None = None) -> str | None:
    """Fetch *url* using *client* or the module-level default."""
    return (client or get_fetch_client()).fetch(url, headers)
