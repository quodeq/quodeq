"""Thread-safe HTTP fetcher with circuit breaker for knowledge refresh."""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)


def _is_private_hostname(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback/link-local address."""
    if hostname in ("localhost", "localhost.localdomain"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        pass
    try:
        for _fam, _typ, _pro, _can, sockaddr in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, OSError):
        pass
    return False


class FetchClient:
    """Thread-safe HTTP fetcher with circuit breaker (trips after repeated failures)."""

    _CIRCUIT_THRESHOLD = 5

    def __init__(self, timeout_s: int = 15, allow_private: bool | None = None) -> None:
        self._lock = threading.Lock()
        self._failures = 0
        self._timeout = timeout_s
        self._allow_private = allow_private

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
        allow_private = self._allow_private if self._allow_private is not None else (os.environ.get("QUODEQ_ALLOW_PRIVATE_URLS") == "1")
        if hostname and _is_private_hostname(hostname) and not allow_private:
            _logger.warning("Blocked fetch to private/internal address: %s", hostname)
            return None

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


def set_fetch_client(client: FetchClient | None) -> None:
    """Replace or clear the module-level fetch client (e.g. for testing)."""
    global _fetch_client_instance
    with _fetch_client_lock:
        _fetch_client_instance = client


def fetch_url(url: str, headers: dict | None = None, *, client: FetchClient | None = None) -> str | None:
    """Fetch *url* using *client* or the module-level default."""
    return (client or get_fetch_client()).fetch(url, headers)
