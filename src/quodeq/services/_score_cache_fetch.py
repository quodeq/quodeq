"""Read-through wrappers over the score-cache tables.

Each one is hit -> return cached, miss -> compute + persist best-effort. The
kill switch (``QUODEQ_DISABLE_SCORE_CACHE``) and any SQLite error degrade to a
plain recompute, so no caller has to handle cache failure.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import DimensionResult
from quodeq.services._score_cache_stale import recall, refresh_in_background, remember
from quodeq.services.wiring import (
    open_score_cache,
    read_all_cached_rows,
    read_cached_accumulated,
    read_cached_project_summary,
    write_cached_accumulated,
    write_cached_project_summary,
    write_cached_rows,
)
from quodeq.shared.env import score_cache_disabled


def _log_write_failure(operation: str, exc: sqlite3.Error, *, log: LogSink) -> None:
    """Log a best-effort cache write failure before degrading to recompute.

    A persistently broken cache (disk full, corrupt DB) must not be silently
    invisible -- every request would keep paying full recompute cost with no
    signal anywhere. The caller still degrades exactly as before; this only
    adds visibility. ``log`` defaults to :data:`NULL_LOG`, matching the
    injected-LogSink discipline for inner layers -- see
    ``quodeq.core.observability``. ``_fs_metadata.py``, ``trend_fetcher.py``
    and ``scoring/_project_scores.py`` thread ``log=SHARED_LOG`` through their
    calls to ``cached_project_summary``, ``make_cache_backed_fetcher`` and
    ``cached_accumulated`` respectively.
    """
    log.warning(f"score-cache write failed for {operation}, degrading to recompute: {exc}")


# In-flight computes by (kind, project, version). Concurrent misses on the
# same key must share ONE compute: these computes walk a project's full run
# history and can take minutes right after an upgrade invalidates every
# cached row, and the client re-requests while the first compute is still
# running. The registry entry is dropped once no thread holds the key's lock;
# a waiter that raced the cleanup at worst recomputes (idempotent write).
_INFLIGHT_GUARD = threading.Lock()
_INFLIGHT: dict[tuple[str, str, str], threading.Lock] = {}


@contextmanager
def _single_flight(kind: str, project: str, version: str) -> Iterator[None]:
    key = (kind, project, version)
    with _INFLIGHT_GUARD:
        lock = _INFLIGHT.setdefault(key, threading.Lock())
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _INFLIGHT_GUARD:
            if not lock.locked() and _INFLIGHT.get(key) is lock:
                del _INFLIGHT[key]


@dataclass(frozen=True)
class CacheTable:
    """One read-through score-cache table: how to read and write its rows."""

    kind: str
    label: str
    read: Callable[[sqlite3.Connection, str, str], dict | None]
    write: Callable[[sqlite3.Connection, str, str, dict], None]
    write_name: str


@dataclass(frozen=True)
class CacheSlot:
    """One read-through cache slot: which table, and the (project, version) key.

    Bundled so ``read_through`` -- which also takes compute/cacheable/log/
    enabled -- stays within the 6-parameter limit.
    """

    table: CacheTable
    project: str
    version: str


def read_through(
    slot: CacheSlot, compute: Callable[[], dict],
    cacheable: Callable[[dict], bool] | None, log: LogSink, enabled: bool,
) -> dict:
    """Hit -> the cached payload. Miss -> compute, cache best-effort, return.

    *enabled* is the resolved kill-switch state (the caller reads
    QUODEQ_DISABLE_SCORE_CACHE once and passes the result in -- this function
    never reads the environment itself). False, or a failed first read,
    degrades to a plain compute. Concurrent misses on one (table, project,
    version) share one compute; the waiter re-checks the cache before
    computing. *cacheable* returning False serves the result without
    persisting it. A failed write is logged through *log* and the computed
    result is still returned.
    """
    table, project, version = slot.table, slot.project, slot.version
    if not enabled:
        return compute()
    try:
        with open_score_cache() as conn:
            cached = table.read(conn, project, version)
        if cached is not None:
            return cached
    except sqlite3.Error:
        return compute()
    with _single_flight(table.kind, project, version):
        # Re-check: a caller we waited on may have computed and cached it.
        try:
            with open_score_cache() as conn:
                cached = table.read(conn, project, version)
            if cached is not None:
                return cached
        except sqlite3.Error as exc:
            log.debug(f"score-cache re-check read failed for {table.label} {project}: {exc}")
        result = compute()
        if cacheable is not None and not cacheable(result):
            return result
        try:
            with open_score_cache() as conn:
                table.write(conn, project, version, result)
        except sqlite3.Error as exc:
            _log_write_failure(table.write_name, exc, log=log)
        return result


def _peek(table: CacheTable, project: str, version: str) -> dict | None:
    """The exact-version cached payload, or None on a miss or SQLite error."""
    try:
        with open_score_cache() as conn:
            return table.read(conn, project, version)
    except sqlite3.Error:
        return None


def cached_accumulated(
    project: str, version: str, compute: Callable[[], dict],
    cacheable: Callable[[dict], bool] | None = None,
    *, stale_scope: str | None = None, log: LogSink = NULL_LOG,
) -> dict:
    """Read-through cache for the accumulated payload (see ``read_through``).

    *cacheable*, when given, is called with the computed result before it is
    persisted; returning False serves the result without caching it. This lets
    the caller withhold payloads it knows are incomplete (e.g. a rescore that
    covered only part of the dimensions), which would otherwise freeze under a
    version hash that cannot self-invalidate.

    *stale_scope* (``score_cache.accumulated_stale_scope``) opts into
    stale-while-revalidate: an exact-version miss inside the same scope serves
    the scope's last payload and refreshes it once in the background (see
    ``_score_cache_stale``). Without a stored payload, the miss computes
    synchronously as before.

    *log* receives a warning if the best-effort cache write or a background
    refresh fails; defaults to a silent no-op (``NULL_LOG``).
    """
    table = CacheTable("accumulated", "accumulated", read_cached_accumulated,
                        write_cached_accumulated, "write_cached_accumulated")
    # Resolved once here (the composition point for this read-through call),
    # not inside read_through, which takes the resolved bool.
    enabled = not score_cache_disabled()
    cache_slot = CacheSlot(table, project, version)
    if stale_scope is None or not enabled:
        return read_through(cache_slot, compute, cacheable, log, enabled)
    slot = (table.kind, project, stale_scope)
    hit = _peek(table, project, version)
    if hit is not None:
        remember(slot, hit)
        return hit

    def fresh() -> dict:
        return read_through(cache_slot, compute, cacheable, log, enabled)

    stale = recall(slot)
    if stale is None:
        payload = fresh()
        remember(slot, payload)
        return payload
    refresh_in_background(slot, fresh, log)
    return stale


def cached_project_summary(
    project: str, version: str, compute: Callable[[], dict],
    *, log: LogSink = NULL_LOG,
) -> dict:
    """Read-through cache for the project-card summary (see ``read_through``).

    *log* receives a warning if the best-effort cache write fails; defaults to
    a silent no-op (``NULL_LOG``), but ``_fs_metadata.py`` threads
    ``log=SHARED_LOG`` through both of its production call sites, so a write
    failure reaches a real sink there.
    """
    table = CacheTable("summary", "project summary", read_cached_project_summary,
                        write_cached_project_summary, "write_cached_project_summary")
    return read_through(
        CacheSlot(table, project, version), compute, None, log, not score_cache_disabled(),
    )


def make_cache_backed_fetcher(
    project: str, version_for: Callable[[str], str],
    base_fetcher: Callable[[str], list[DimensionResult]],
    is_cacheable: Callable[[str], bool] | None = None, *, log: LogSink = NULL_LOG,
) -> Callable[[str], list[DimensionResult]]:
    """Wrap *base_fetcher* with the read-through cache, versioned PER RUN.

    *version_for(run_id)* returns that run's scoped version (params + the
    suppressions touching it). Bulk-loads every cached row for *project* keyed by
    (run_id, version); a hit requires the row's version to equal the run's
    current version, so a dismiss/delete only misses the runs it touches. Misses
    compute via *base_fetcher*, cache scalars at the run's version (only when
    ``is_cacheable``), and return them. Kill switch -> *base_fetcher* unchanged.

    ``is_cacheable`` gates *persistence* per run: only terminal (complete) runs
    are safe. An in-progress run's scalar set grows as dimensions finish, and the
    version hash can't see that, so persisting its partial set would strand a
    stale row -- so opening History mid-scan would leave the trend showing one
    dimension forever while run-detail shows all six. Non-cacheable runs
    compute-through and are served for the current build but never written to
    disk. Defaults to "always cacheable" for backward compatibility.
    """
    if score_cache_disabled():
        return base_fetcher

    try:
        with open_score_cache() as conn:
            by_run_version = read_all_cached_rows(conn, project)
    except sqlite3.Error:
        by_run_version = {}

    def fetch(run_id: str) -> list[DimensionResult]:
        version = version_for(run_id)
        hit = by_run_version.get((run_id, version))
        if hit is not None:
            return hit
        dims = base_fetcher(run_id)
        scalars = [DimensionResult(dimension=d.dimension, overall_score=d.overall_score,
                                   overall_grade=d.overall_grade)
                   for d in dims if d.dimension]
        by_run_version[(run_id, version)] = scalars
        if is_cacheable is None or is_cacheable(run_id):
            try:
                with open_score_cache() as conn:
                    write_cached_rows(conn, project, run_id, version, scalars)
            except sqlite3.Error as exc:
                _log_write_failure("write_cached_rows", exc, log=log)
        return scalars

    return fetch
