"""Singleton management and convenience wrapper for FetchClient.

The FetchClient class itself lives in ``_fetch_client_class``.
"""
from __future__ import annotations

import threading

from quodeq.config._fetch_client_class import FetchClient  # noqa: F401


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
