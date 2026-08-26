"""Read-through wrappers over the score-cache tables.

Each one is hit -> return cached, miss -> compute + persist best-effort. The
kill switch (``QUODEQ_DISABLE_SCORE_CACHE``) and any SQLite error degrade to a
plain recompute, so no caller has to handle cache failure.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Callable, Iterator

from quodeq.core.types import DimensionResult
from quodeq.services._score_cache_db import open_score_cache
from quodeq.services._score_cache_store import (
    read_cached_accumulated,
    read_cached_project_summary,
    write_cached_accumulated,
    write_cached_project_summary,
    write_cached_rows,
)
from quodeq.shared._env import score_cache_disabled

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


def cached_accumulated(
    project: str, version: str, compute: Callable[[], dict],
    cacheable: Callable[[dict], bool] | None = None,
) -> dict:
    """Read-through cache for the accumulated payload.

    Hit -> return the deserialized cached payload. Miss (or kill switch / cache
    error) -> call *compute*, cache the result best-effort, return it.
    Concurrent misses on one (project, version) share a single compute.

    *cacheable*, when given, is called with the computed result before it is
    persisted; returning False serves the result without caching it. This lets
    the caller withhold payloads it knows are incomplete (e.g. a rescore that
    covered only part of the dimensions), which would otherwise freeze under a
    version hash that cannot self-invalidate.
    """
    if score_cache_disabled():
        return compute()
    try:
        with open_score_cache() as conn:
            cached = read_cached_accumulated(conn, project, version)
        if cached is not None:
            return cached
    except sqlite3.Error:
        return compute()
    with _single_flight("accumulated", project, version):
        # Re-check: a caller we waited on may have computed and cached it.
        try:
            with open_score_cache() as conn:
                cached = read_cached_accumulated(conn, project, version)
            if cached is not None:
                return cached
        except sqlite3.Error:
            pass
        result = compute()
        if cacheable is not None and not cacheable(result):
            return result
        try:
            with open_score_cache() as conn:
                write_cached_accumulated(conn, project, version, result)
        except sqlite3.Error:
            pass
        return result


def cached_project_summary(
    project: str, version: str, compute: Callable[[], dict],
) -> dict:
    """Read-through cache for the project-card summary (mirrors cached_accumulated)."""
    if score_cache_disabled():
        return compute()
    try:
        with open_score_cache() as conn:
            hit = read_cached_project_summary(conn, project, version)
        if hit is not None:
            return hit
    except sqlite3.Error:
        return compute()
    with _single_flight("summary", project, version):
        # Re-check: a caller we waited on may have computed and cached it.
        try:
            with open_score_cache() as conn:
                hit = read_cached_project_summary(conn, project, version)
            if hit is not None:
                return hit
        except sqlite3.Error:
            pass
        result = compute()
        try:
            with open_score_cache() as conn:
                write_cached_project_summary(conn, project, version, result)
        except sqlite3.Error:
            pass
        return result


def make_cache_backed_fetcher(
    project: str, version_for: Callable[[str], str],
    base_fetcher: Callable[[str], list[DimensionResult]],
    is_cacheable: Callable[[str], bool] | None = None,
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

    by_run_version: dict[tuple[str, str], list[DimensionResult]] = {}
    try:
        with open_score_cache() as conn:
            for rid, ver, dim, score, grade in conn.execute(
                "SELECT run_id, version, dimension, overall_score, overall_grade "
                "FROM run_scalars WHERE project=? ORDER BY run_id, dimension",
                (project,),
            ):
                by_run_version.setdefault((rid, ver), []).append(
                    DimensionResult(dimension=dim, overall_score=score, overall_grade=grade))
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
            except sqlite3.Error:
                pass
        return scalars

    return fetch
