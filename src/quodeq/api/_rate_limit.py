"""Rate-limit store abstractions for the Quodeq API."""
from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Protocol, runtime_checkable

_logger = logging.getLogger(__name__)

_DEFAULT_RATE_LIMIT_WINDOW = 60
_DEFAULT_RATE_LIMIT_MAX = 60
_RATE_STORE_MAX_IPS = 10_000  # max tracked IPs to prevent unbounded memory growth
_PRUNE_THRESHOLD_MULTIPLIER = 2  # prune per-IP list when it exceeds max_requests * this


def _rate_limit_window(env: dict[str, str] | None = None) -> int:
    """Return the rate-limit window in seconds."""
    return int((env or os.environ).get("QUODEQ_RATE_LIMIT_WINDOW", str(_DEFAULT_RATE_LIMIT_WINDOW)))


def _rate_limit_max(env: dict[str, str] | None = None) -> int:
    """Return the maximum number of requests per window."""
    return int((env or os.environ).get("QUODEQ_RATE_LIMIT_MAX", str(_DEFAULT_RATE_LIMIT_MAX)))


@runtime_checkable
class RateLimitStore(Protocol):
    """Abstraction for rate-limit state storage.

    Implementations track per-IP request timestamps within a sliding window.
    The default ``InMemoryRateLimitStore`` keeps state in-process; replace with
    a Redis-backed implementation for multi-worker deployments.
    """

    def record(self, ip: str, now: float) -> None:
        """Record a state-changing request from *ip* at time *now*."""
        ...

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit at time *now*."""
        ...


class InMemoryRateLimitStore:
    """Process-local rate-limit store backed by an LRU OrderedDict.

    **Scaling:** This store is per-process. In multi-worker deployments,
    implement ``RateLimitStore`` with a shared backend (e.g. Redis) and
    pass it to ``create_app(rate_limit_store=...)``.
    Set ``QUODEQ_RATE_LIMIT_STORE=redis`` to opt in (requires custom wiring).
    """

    _CLEANUP_INTERVAL = 60  # seconds between full TTL sweeps

    def __init__(
        self,
        window: float | None = None,
        max_requests: int | None = None,
        max_ips: int = _RATE_STORE_MAX_IPS,
    ) -> None:
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._window = window if window is not None else _rate_limit_window()
        self._max_requests = max_requests if max_requests is not None else _rate_limit_max()
        self._max_ips = max_ips
        self._last_cleanup: float = 0.0

    def _evict_stale(self, now: float) -> None:
        if len(self._store) <= self._max_ips:
            return
        stale = []
        for k, v in self._store.items():
            if all(now - t >= self._window for t in v):
                stale.append(k)
            else:
                break  # LRU order: first non-stale entry means the rest are newer
        for k in stale:
            del self._store[k]
        if len(self._store) > self._max_ips:
            self._store.clear()

    def _periodic_cleanup(self, now: float) -> None:
        """Remove all expired entries if enough time has passed since the last sweep."""
        if now - self._last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        stale = [k for k, v in self._store.items() if all(now - t >= self._window for t in v)]
        for k in stale:
            del self._store[k]

    def record(self, ip: str, now: float) -> None:
        """Record a state-changing request from *ip* at time *now*."""
        if not ip:
            return
        self._periodic_cleanup(now)
        timestamps = self._store.setdefault(ip, [])
        timestamps.append(now)
        if len(timestamps) > self._max_requests * _PRUNE_THRESHOLD_MULTIPLIER:
            self._store[ip] = [t for t in timestamps if now - t < self._window]
        self._store.move_to_end(ip)

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit at time *now*."""
        self._evict_stale(now)
        timestamps = [t for t in self._store.get(ip, []) if now - t < self._window]
        if not timestamps:
            self._store.pop(ip, None)
        else:
            self._store[ip] = timestamps
            self._store.move_to_end(ip)
        return len(timestamps) >= self._max_requests


def create_rate_limit_store(env: dict[str, str] | None = None) -> RateLimitStore:
    """Create the default rate-limit store.

    For multi-worker deployments, pass a ``RateLimitStore``-compatible
    shared backend (e.g. Redis) to ``create_app(rate_limit_store=...)``,
    or monkey-patch this factory.  Set ``QUODEQ_RATE_LIMIT_BACKEND`` to
    signal the desired backend (only ``memory`` is built-in).
    """
    backend = (env or os.environ).get("QUODEQ_RATE_LIMIT_BACKEND", "memory")
    if backend != "memory":
        _logger.warning(
            "Unknown rate-limit backend %r — falling back to in-memory. "
            "Pass a custom RateLimitStore to create_app() for shared backends.",
            backend,
        )
    return InMemoryRateLimitStore()
