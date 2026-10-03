"""Read-through wrappers over the score-cache tables.

Each one is hit -> return cached, miss -> compute + persist best-effort. The
kill switch (``QUODEQ_DISABLE_SCORE_CACHE``) and any SQLite error degrade to a
plain recompute, so no caller has to handle cache failure.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import DimensionResult
from quodeq.services.wiring import (
    DEFAULT_SINGLE_FLIGHT,
    SingleFlight,
    open_score_cache,
    read_all_cached_rows,
    read_cached_project_summary,
    row_dimension,
    scalar_dimension,
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
    ``quodeq.core.observability``. ``_fs_metadata.py`` and ``trend_fetcher.py``
    thread ``log=SHARED_LOG`` through their calls to ``cached_project_summary``
    and ``make_cache_backed_fetcher`` respectively.
    """
    log.warning(f"score-cache write failed for {operation}, degrading to recompute: {exc}")


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
    """One read-through cache slot: which table, the (project, version) key,
    and the single-flight registry that serialises concurrent misses on it.

    Bundled so ``read_through`` -- which also takes compute/cacheable/log/
    enabled -- stays within the 6-parameter limit. ``single_flight`` defaults
    to the one process-wide :data:`DEFAULT_SINGLE_FLIGHT`; a caller-supplied
    instance is for test isolation only, never a per-request substitute.
    """

    table: CacheTable
    project: str
    version: str
    single_flight: SingleFlight | None = None


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
        cached = _read_row(table, project, version)
        if cached is not None:
            return cached
    except sqlite3.Error as exc:
        log.warning(f"score-cache read failed for {table.label} {project}: {exc}")
        return compute()
    flight = slot.single_flight if slot.single_flight is not None else DEFAULT_SINGLE_FLIGHT
    with flight.hold((table.kind, project, version)):
        # Re-check: a caller we waited on may have computed and cached it.
        try:
            cached = _read_row(table, project, version)
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


def _read_row(table: CacheTable, project: str, version: str) -> dict | None:
    """The exact-version cached payload, or None on a miss. SQLite errors propagate."""
    with open_score_cache() as conn:
        return table.read(conn, project, version)


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


class RowFetcher:
    """Per-run dimensions served from ``run_scalars`` rows, versioned per run.

    Calling it returns the trend shape (``scalar_dimension``: score, grade,
    counts). ``rows`` returns what the store keeps for the same run: the
    scalars plus files read and principle grades, which the accumulated walk
    needs to pick and grade a winning run without reading its findings. Both
    come from one bulk read of the project's rows; a miss computes the run
    once through *base_fetcher* and serves both shapes from that.
    """

    def __init__(
        self, project: str, version_for: Callable[[str], str],
        base_fetcher: Callable[[str], list[DimensionResult]],
        is_cacheable: Callable[[str], bool] | None, *, log: LogSink,
    ) -> None:
        self._project, self._version_for, self._base = project, version_for, base_fetcher
        self._is_cacheable, self._log = is_cacheable, log
        try:
            with open_score_cache() as conn:
                self._by_run_version = read_all_cached_rows(conn, project)
        except sqlite3.Error as exc:
            log.warning(f"score-cache bulk read failed for {project}: {exc}")
            self._by_run_version = {}

    def __call__(self, run_id: str) -> list[DimensionResult]:
        """The run's dimensions in the trend shape."""
        return [scalar_dimension(d) for d in self.rows(run_id)]

    def rows(self, run_id: str) -> list[DimensionResult]:
        """The run's row dimensions: scalars, files read and principles."""
        version = self._version_for(run_id)
        hit = self._by_run_version.get((run_id, version))
        if hit is not None:
            return hit
        rows = [row_dimension(d) for d in self._base(run_id) if d.dimension]
        self._by_run_version[(run_id, version)] = rows
        if self._is_cacheable is None or self._is_cacheable(run_id):
            try:
                with open_score_cache() as conn:
                    write_cached_rows(conn, self._project, run_id, version, rows)
            except sqlite3.Error as exc:
                _log_write_failure("write_cached_rows", exc, log=self._log)
        return rows


def run_rows(fetcher: Callable[[str], list[DimensionResult]]) -> Callable[[str], list[DimensionResult]]:
    """*fetcher*'s ``rows`` accessor, or the fetcher itself when it has none.

    The cache kill switch and test doubles hand over a plain callable whose
    result already carries every scalar the row readers need.
    """
    return getattr(fetcher, "rows", fetcher)


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
    compute via *base_fetcher*, cache the run's rows at its version (only when
    ``is_cacheable``), and return them. Kill switch -> *base_fetcher* unchanged.

    ``is_cacheable`` gates *persistence* per run: only terminal (complete) runs
    are safe. An in-progress run's scalar set grows as dimensions finish, and the
    version hash can't see that, so persisting its partial set would strand a
    stale row -- so opening History mid-scan would leave the trend showing one
    dimension forever while run-detail shows all six. Non-cacheable runs
    compute-through and are served for the current build but never written to
    disk. Defaults to "always cacheable" for backward compatibility.

    The result is a :class:`RowFetcher` unless the cache is disabled.
    """
    if score_cache_disabled():
        return base_fetcher
    return RowFetcher(project, version_for, base_fetcher, is_cacheable, log=log)
