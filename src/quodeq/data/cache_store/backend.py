"""Cache backend protocol.

Implementations:
- ``LocalFileBackend`` — atomic file writes under ``~/.quodeq/cache/results``.
- ``RemoteHTTPBackend`` (future) — opt-in shared cache via signed URLs.

The protocol is deliberately minimal: get/put/has/delete plus stats.
Anything richer (bulk ops, prefix queries) can be added when a concrete
need shows up.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quodeq.data.cache_store.entry import CacheEntry


@dataclass
class CacheStats:
    """Size of a backend's stored set, as reported by ``CacheBackend.stats``."""

    entries: int
    bytes: int


class CacheBackend(Protocol):
    """Storage boundary for cache entries, keyed by opaque cache-key strings."""

    def get(self, key: str) -> CacheEntry | None:
        """Return the entry stored under *key*, or None if nothing is stored."""
        ...

    def put(self, key: str, entry: CacheEntry) -> None:
        """Store *entry* under *key*, replacing any previous value."""
        ...

    def has(self, key: str) -> bool:
        """Report whether *key* is present, without decoding the entry."""
        ...

    def delete(self, key: str) -> None:
        """Drop *key*. A missing key is not an error."""
        ...

    def stats(self) -> CacheStats:
        """Return the current entry count and total bytes on disk."""
        ...
