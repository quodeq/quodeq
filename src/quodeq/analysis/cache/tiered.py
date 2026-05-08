"""Tiered cache — local-first with optional remote fallback.

The remote tier is intentionally unimplemented in this PR. The shape is
fixed now so that adding an HTTP/S3-backed ``CacheBackend`` later is a
small, isolated change rather than a refactor.
"""
from __future__ import annotations

import logging

from quodeq.analysis.cache.backend import CacheBackend, CacheStats
from quodeq.analysis.cache.entry import CacheEntry

_logger = logging.getLogger(__name__)


class TieredCache:
    """Composes a local backend with an optional remote backend.

    Read path: local hit returns immediately; on miss, remote is tried and
    a remote hit warms the local tier before returning. Write path:
    always writes local; remote write is best-effort and never raises.
    """

    def __init__(self, local: CacheBackend, remote: CacheBackend | None = None) -> None:
        self._local = local
        self._remote = remote

    def get(self, key: str) -> CacheEntry | None:
        if hit := self._local.get(key):
            return hit
        if self._remote is None:
            return None
        try:
            hit = self._remote.get(key)
        except Exception as exc:  # noqa: BLE001 — remote failures must never propagate
            _logger.warning("remote cache get failed for %s: %s", key, exc)
            return None
        if hit is None:
            return None
        self._local.put(key, hit)
        return hit

    def put(self, key: str, entry: CacheEntry) -> None:
        self._local.put(key, entry)
        if self._remote is None:
            return
        try:
            self._remote.put(key, entry)
        except Exception as exc:  # noqa: BLE001 — remote failures must never propagate
            _logger.warning("remote cache put failed for %s: %s", key, exc)

    def has(self, key: str) -> bool:
        if self._local.has(key):
            return True
        if self._remote is None:
            return False
        try:
            return self._remote.has(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("remote cache has failed for %s: %s", key, exc)
            return False

    def delete(self, key: str) -> None:
        self._local.delete(key)
        if self._remote is None:
            return
        try:
            self._remote.delete(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("remote cache delete failed for %s: %s", key, exc)

    def stats(self) -> CacheStats:
        return self._local.stats()
