"""Thread-safe mtime-based cache for the project index file."""
from __future__ import annotations

import threading
from pathlib import Path

_INDEX_CACHE_MAX = 64


class _IndexCache:
    """Thread-safe mtime-based cache for the project index file (bounded)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[Path, tuple[float, dict[str, str]]] = {}

    def get(self, key: Path) -> tuple[float, dict[str, str]] | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: Path, value: tuple[float, dict[str, str]]) -> None:
        with self._lock:
            if len(self._data) >= _INDEX_CACHE_MAX and key not in self._data:
                # Evict oldest entry
                oldest = next(iter(self._data))
                del self._data[oldest]
            self._data[key] = value

    def pop(self, key: Path) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


# Module-level singleton for mtime-based project index caching.
# Thread-safe via internal locking (_IndexCache._lock).  Bounded to
# _INDEX_CACHE_MAX entries to prevent unbounded memory growth.
# Call index_cache.clear() (or clear_index_cache()) in tests for isolation.
index_cache = _IndexCache()


def clear_index_cache() -> None:
    """Clear the mtime-based index cache (useful for testing and isolation)."""
    index_cache.clear()
