"""Score-cache operations that own their connection.

Code above the data layer calls these instead of opening the cache and
catching driver errors itself. Each one opens the cache (or joins the active
``score_cache_session``), runs its store calls and closes it. A SQLite failure
or an unreachable cache directory surfaces as :class:`ScoreCacheError`, so a
caller degrades to a recompute without importing ``sqlite3``. The store's
writes already skip a cache opened read-only.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import ExitStack, contextmanager

from quodeq.core.types import DimensionResult
from quodeq.data.sqlite.score_cache_db import open_score_cache
from quodeq.data.sqlite.score_cache_forget import forget_projects
from quodeq.data.sqlite.score_cache_store import (
    load_run_changes,
    load_run_key_sets,
    prune_run_changes,
    read_all_cached_rows,
    read_cached_project_summary,
    store_run_change,
    store_run_keys,
    write_cached_project_summary,
    write_cached_rows,
)

KeySets = tuple[set[tuple], set[tuple]]


class ScoreCacheError(Exception):
    """The score cache could not be opened, read or written.

    ``__cause__`` is the driver error, or the OSError of a cache directory
    that cannot be created or reached.
    """


@contextmanager
def _cache() -> Iterator[sqlite3.Connection]:
    try:
        with open_score_cache() as conn:
            yield conn
    except (sqlite3.Error, OSError) as exc:
        raise ScoreCacheError(str(exc)) from exc


def read_project_summary(project: str, version: str) -> dict | None:
    """The cached project-card summary at *version*, or None on a miss."""
    with _cache() as conn:
        return read_cached_project_summary(conn, project, version)


def write_project_summary(project: str, version: str, payload: dict) -> None:
    """Cache the project-card summary at *version* (best-effort)."""
    with _cache() as conn:
        write_cached_project_summary(conn, project, version, payload)


def read_project_rows(project: str) -> dict[tuple[str, str], list[DimensionResult]]:
    """Every cached row dimension of *project*, keyed by ``(run_id, version)``."""
    with _cache() as conn:
        return read_all_cached_rows(conn, project)


def write_run_rows(project: str, run_id: str, version: str, rows: list[DimensionResult]) -> None:
    """Replace the run's cached row dimensions with *rows* at *version* (best-effort)."""
    with _cache() as conn:
        write_cached_rows(conn, project, run_id, version, rows)


def take_run_changes(project: str, keys: dict[str, str]) -> dict[str, dict]:
    """The cached change data of *keys*' runs, then drop *project*'s rows for every other run."""
    with _cache() as conn:
        cached = load_run_changes(conn, project, keys)
        prune_run_changes(conn, project, set(keys))
    return cached


def save_run_change(project: str, run_id: str, key: str, payload: dict) -> None:
    """Cache one run's History change data under *key* (best-effort)."""
    with _cache() as conn:
        store_run_change(conn, project, run_id, key, payload)


def forget_project_scores(projects: Iterable[str]) -> None:
    """Drop every cached row of *projects* (deleted projects, best-effort)."""
    with _cache() as conn:
        forget_projects(conn, projects)


def save_run_keys(project: str, run_id: str, dismiss_keys: set[tuple], class_keys: set[tuple]) -> None:
    """Persist a run's key sets (best-effort)."""
    with _cache() as conn:
        store_run_keys(conn, project, run_id, dismiss_keys, class_keys)


def persisted_run_key_sets(project: str, run_id: str) -> KeySets | None:
    """One run's persisted key sets; None when absent or when the cache cannot be read.

    Only terminal runs are ever persisted, so a cancelled or in-flight run
    answers None cheaply, without decoding any other run's blobs.
    """
    try:
        with _cache() as conn:
            return load_run_key_sets(conn, project, run_id)
    except ScoreCacheError:
        return None


class RunKeyStore:
    """Persisted run key sets over one open cache connection.

    Built without a connection (the cache could not be opened) it finds
    nothing and keeps nothing, so callers read the key sets from disk.
    """

    def __init__(self, conn: sqlite3.Connection | None) -> None:
        self._conn = conn

    def load(self, project: str, run_id: str) -> KeySets | None:
        """The run's persisted key sets, or None when absent or unavailable."""
        return None if self._conn is None else load_run_key_sets(self._conn, project, run_id)

    def save(self, project: str, run_id: str, keys: KeySets) -> None:
        """Persist the run's key sets (best-effort; nothing without a connection)."""
        if self._conn is not None:
            store_run_keys(self._conn, project, run_id, keys[0], keys[1])


@contextmanager
def run_key_store() -> Iterator[RunKeyStore]:
    """One cache connection for a batch of run key reads and writes.

    An unopenable cache yields a store without a connection instead of raising.
    """
    with ExitStack() as stack:
        try:
            conn = stack.enter_context(open_score_cache())
        except (sqlite3.Error, OSError):
            conn = None
        yield RunKeyStore(conn)
