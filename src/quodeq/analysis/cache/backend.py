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

from quodeq.analysis.cache.entry import CacheEntry


@dataclass
class CacheStats:
    entries: int
    bytes: int


class CacheBackend(Protocol):
    def get(self, key: str) -> CacheEntry | None: ...
    def put(self, key: str, entry: CacheEntry) -> None: ...
    def has(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def stats(self) -> CacheStats: ...
