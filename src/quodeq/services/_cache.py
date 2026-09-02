"""Shared LRU cache factory for dimension fetchers.

Thread-safe LRU cache with per-key inflight coordination to prevent
duplicate I/O when multiple threads request the same uncached key.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from quodeq.data.fs.report_parser.runs import read_run_data
from quodeq.data.fs.run_files import count_eval_files, read_run_state
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


# Terminal status.json states, mirroring data/fs/report_parser/runs.py. Any
# other state means the run's evaluation/ set may still be growing.
_TERMINAL_RUN_STATES = frozenset({"done", "failed", "cancelled"})


def _count_eval_files(reports_root: Path, project: str, run_id: str) -> int:
    """Count ``evaluation/*.json`` files on disk for a run.

    Used to detect a stale cache: if the cached dim list has a different
    count from what's currently on disk, the cache is wrong and must be
    evicted. One ``listdir`` per cached lookup -- cheap. The read itself
    lives in the data layer; a missing directory counts as 0 here.
    """
    return count_eval_files(reports_root / project / run_id) or 0


def _run_is_in_progress(reports_root: Path, project: str, run_id: str) -> bool:
    """True when the run's ``status.json`` reports a non-terminal state.

    A missing or unreadable status.json counts as terminal: legacy runs never
    wrote one and their data is immutable. The PID-liveness refinement in
    ``data/fs/report_parser/runs.py`` is deliberately not replicated here -- a
    run that crashed without flipping its state reads fresh forever, which is
    the safe direction for a cache guard.
    """
    state = read_run_state(reports_root / project / run_id)
    return state is not None and state not in _TERMINAL_RUN_STATES


def _cached_entry_is_stale(
    reports_root: Path, project: str, run_id: str, cached: list[DimensionResult],
) -> bool:
    """True when the cached dim count disagrees with ``evaluation/*.json`` on disk.

    Anchored on the evaluation/ directory existing: without disk state to
    compare against (unit tests that pre-seed the cache), the entry is trusted.
    """
    on_disk = count_eval_files(reports_root / project / run_id)
    if on_disk is None:
        return False
    return len(cached) != on_disk


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


def _get_run_dimensions(
    run_id: str, reports_root: Path, project: str, version: str, ctx: _CacheContext,
) -> list[DimensionResult]:
    key = (reports_root, project, run_id, version)

    cached = _cache_lookup(key, ctx)
    if cached is not None:
        if not _cached_entry_is_stale(reports_root, project, run_id, cached):
            return cached
        with ctx.lock:
            ctx.cache.pop(key, None)

    if _run_is_in_progress(reports_root, project, run_id):
        return _fetch_dimensions_from_disk(
            reports_root, project, run_id, ctx.get_reader(),
        )

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


def make_lru_dimension_fetcher(
    reports_root: Path,
    project: str,
    cache: OrderedDict[tuple, list[DimensionResult]],
    lock: threading.Lock,
    max_size: int,
    reader: _Reader | None = None,
    version: str = "",
) -> Callable[[str], list[DimensionResult]]:
    """Return a callable that fetches dimension data for a run.

    Results are stored in *cache* (LRU, bounded at *max_size* entries) so
    repeated calls within and across requests avoid redundant file reads.

    Concurrency model: a per-key ``threading.Event`` in *_inflight* ensures
    that at most one thread performs disk I/O for any given cache key.  Other
    threads that request the same key while I/O is in progress wait on the
    event and then read the result from the cache.

    Self-healing guards (every caller inherits them, so a request landing
    mid-run can never freeze a partial dim list in the cache):

    1. **On-disk count validation.** A cached entry whose dim count disagrees
       with the run's ``evaluation/*.json`` count is stale (e.g. it was
       populated while the run was still writing dims) -- evict and re-read.
       Only applies when an evaluation/ directory exists on disk; entries
       pre-seeded without disk state (test stubs) are trusted.

    2. **In-progress bypass.** Runs whose ``status.json`` state is non-terminal
       have a growing evaluation/ set. Read directly from disk and don't
       cache, so the next request also reads fresh.
    """
    ctx = _CacheContext(cache=cache, lock=lock, max_size=max_size, reader=reader)

    def get_run_dimensions(run_id: str) -> list[DimensionResult]:
        return _get_run_dimensions(run_id, reports_root, project, version, ctx)

    return get_run_dimensions
