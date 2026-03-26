"""Shared LRU cache factory for dimension fetchers.

Thread-safe LRU cache with per-key inflight coordination to prevent
duplicate I/O when multiple threads request the same uncached key.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from quodeq.adapters.fs.report_parser import read_run_data
from quodeq.core.types import DimensionResult

_logger = logging.getLogger(__name__)


def _fetch_dimensions_from_disk(
    reports_root: Path, project: str, run_id: str,
) -> list[DimensionResult]:
    """Read dimension data from disk with error handling.

    This is the I/O boundary — intentionally called outside any cache lock
    so that slow reads do not block other cache lookups.  Per-key mutual
    exclusion is guaranteed by the inflight-event mechanism in the caller.
    """
    try:
        return read_run_data(reports_root, project, run_id)
    except (OSError, ValueError, KeyError) as exc:
        _logger.warning(
            "Failed to read run data for %s/%s: %s", project, run_id, exc,
        )
        return []


def make_lru_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]],
    lock: threading.Lock,
    max_size: int,
) -> Callable[[str], list[DimensionResult]]:
    """Return a callable that fetches dimension data for a run.

    Results are stored in *cache* (LRU, bounded at *max_size* entries) so
    repeated calls within and across requests avoid redundant file reads.

    Concurrency model: a per-key ``threading.Event`` in *_inflight* ensures
    that at most one thread performs disk I/O for any given cache key.  Other
    threads that request the same key while I/O is in progress wait on the
    event and then read the result from the cache.
    """
    _inflight: dict[tuple, threading.Event] = {}

    def _cache_lookup(key: tuple) -> list[DimensionResult] | None:
        """Return cached data for *key* (promoting it in LRU order), or None."""
        with lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        return None

    def _cache_store(key: tuple, data: list[DimensionResult]) -> None:
        """Insert *data* into the cache under *key*, evicting if necessary."""
        with lock:
            cache[key] = data
            cache.move_to_end(key)
            while len(cache) > max_size:
                cache.popitem(last=False)

    def get_run_dimensions(run_id: str) -> list[DimensionResult]:
        key = (reports_root, project, run_id)

        # Fast path: already cached
        cached = _cache_lookup(key)
        if cached is not None:
            return cached

        # Coordinate concurrent misses via per-key events
        with lock:
            # Double-check after acquiring lock
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            existing = _inflight.get(key)
            if existing is not None:
                wait_event = existing
            else:
                wait_event = None
                _inflight[key] = threading.Event()

        if wait_event is not None:
            wait_event.wait(timeout=30)
            with lock:
                return list(cache.get(key, []))

        # This thread is responsible for the fetch
        data = _fetch_dimensions_from_disk(reports_root, project, run_id)

        if data:
            _cache_store(key, data)

        with lock:
            notify_event = _inflight.pop(key, None)
        if notify_event is not None:
            notify_event.set()

        return data

    return get_run_dimensions
