"""Shared LRU cache factory for dimension fetchers.

Thread-safe LRU cache with per-key inflight coordination to prevent
duplicate I/O when multiple threads request the same uncached key.
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from quodeq.services.ports import read_run_data
from quodeq.core.types import DimensionResult

_logger = logging.getLogger(__name__)

_CACHE_WAIT_TIMEOUT_S = 30

_Reader = Callable[[Path, str, str], list[DimensionResult]]


@dataclass
class _CacheContext:
    """Grouped cache state used by internal cache helpers."""
    cache: OrderedDict
    lock: threading.Lock
    max_size: int
    reader: _Reader | None = None
    inflight: dict[tuple, threading.Event] = field(default_factory=dict)

    def get_reader(self) -> _Reader:
        """Return the configured reader, defaulting to read_run_data."""
        return self.reader if self.reader is not None else read_run_data


def _fetch_dimensions_from_disk(
    reports_root: Path, project: str, run_id: str, reader: _Reader | None = None,
) -> list[DimensionResult]:
    """Read dimension data from disk with error handling.

    This is the I/O boundary — intentionally called outside any cache lock
    so that slow reads do not block other cache lookups.  Per-key mutual
    exclusion is guaranteed by the inflight-event mechanism in the caller.
    """
    _reader = reader if reader is not None else read_run_data
    try:
        return _reader(reports_root, project, run_id)
    except (OSError, ValueError, KeyError) as exc:
        _logger.warning(
            "Failed to read run data for %s/%s: %s", project, run_id, exc,
        )
        return []


def _cache_lookup(
    key: tuple, ctx: _CacheContext,
) -> list[DimensionResult] | None:
    """Return cached data for *key* (promoting it in LRU order), or None."""
    with ctx.lock:
        if key in ctx.cache:
            ctx.cache.move_to_end(key)
            return ctx.cache[key]
    return None


def _cache_store(
    key: tuple, data: list[DimensionResult], ctx: _CacheContext,
) -> None:
    """Insert *data* into the cache under *key*, evicting if necessary."""
    with ctx.lock:
        ctx.cache[key] = data
        ctx.cache.move_to_end(key)
        while len(ctx.cache) > ctx.max_size:
            ctx.cache.popitem(last=False)


def _wait_for_inflight(
    key: tuple, event: threading.Event, ctx: _CacheContext,
) -> list[DimensionResult]:
    """Wait for another thread's in-flight fetch and return the cached result."""
    event.wait(timeout=_CACHE_WAIT_TIMEOUT_S)
    with ctx.lock:
        return list(ctx.cache.get(key, []))


def _fetch_and_store(
    key: tuple, reports_root: Path, project: str, run_id: str,
    ctx: _CacheContext,
) -> list[DimensionResult]:
    """Perform the disk fetch, store in cache, and notify waiters."""
    data = _fetch_dimensions_from_disk(reports_root, project, run_id, ctx.get_reader())
    if data:
        _cache_store(key, data, ctx)
    with ctx.lock:
        notify_event = ctx.inflight.pop(key, None)
    if notify_event is not None:
        notify_event.set()
    return data


def make_lru_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]],
    lock: threading.Lock,
    max_size: int,
    reader: _Reader | None = None,
) -> Callable[[str], list[DimensionResult]]:
    """Return a callable that fetches dimension data for a run.

    Results are stored in *cache* (LRU, bounded at *max_size* entries) so
    repeated calls within and across requests avoid redundant file reads.

    Concurrency model: a per-key ``threading.Event`` in *_inflight* ensures
    that at most one thread performs disk I/O for any given cache key.  Other
    threads that request the same key while I/O is in progress wait on the
    event and then read the result from the cache.
    """
    ctx = _CacheContext(cache=cache, lock=lock, max_size=max_size, reader=reader)

    def get_run_dimensions(run_id: str) -> list[DimensionResult]:
        key = (reports_root, project, run_id)

        cached = _cache_lookup(key, ctx)
        if cached is not None:
            return cached

        with ctx.lock:
            if key in ctx.cache:
                ctx.cache.move_to_end(key)
                return ctx.cache[key]
            existing = ctx.inflight.get(key)
            if existing is not None:
                wait_event = existing
            else:
                wait_event = None
                ctx.inflight[key] = threading.Event()

        if wait_event is not None:
            return _wait_for_inflight(key, wait_event, ctx)

        return _fetch_and_store(
            key, reports_root, project, run_id, ctx,
        )

    return get_run_dimensions
