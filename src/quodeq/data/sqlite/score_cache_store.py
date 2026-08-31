"""Row-level reads/writes for the score-cache tables.

One function per (table, direction). Every write is best-effort: it logs and
returns on any SQLite/serialization error, because the caller already holds the
computed value and the cache is disposable. Every read returns None/empty on
error so the caller falls through to recompute.
"""
from __future__ import annotations

import json
import logging
import sqlite3

from quodeq.core.types import DimensionResult
from quodeq.data.sqlite.score_cache_db import open_score_cache

_logger = logging.getLogger(__name__)


def read_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
) -> list[DimensionResult] | None:
    """Return cached scalar dims for (project, run_id, version), or None on miss/error."""
    try:
        rows = conn.execute(
            "SELECT dimension, overall_score, overall_grade FROM run_scalars "
            "WHERE project=? AND run_id=? AND version=? ORDER BY dimension",
            (project, run_id, version),
        ).fetchall()
    except sqlite3.Error:
        return None
    if not rows:
        return None
    return [DimensionResult(dimension=r[0], overall_score=r[1], overall_grade=r[2]) for r in rows]


def write_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
    dims: list[DimensionResult],
) -> None:
    """Replace all cached rows for (project, run_id) with *dims* at *version*.

    Best-effort: logs and returns on any SQLite error (the caller still has the
    computed result).
    """
    try:
        conn.execute("DELETE FROM run_scalars WHERE project=? AND run_id=?", (project, run_id))
        conn.executemany(
            "INSERT OR REPLACE INTO run_scalars "
            "(project, run_id, version, dimension, overall_score, overall_grade) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(project, run_id, version, d.dimension, d.overall_score, d.overall_grade)
             for d in dims if d.dimension],
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("score cache write failed for %s/%s", project, run_id, exc_info=True)


def read_cached_accumulated(
    conn: sqlite3.Connection, project: str, version: str,
) -> dict | None:
    """Return the cached accumulated payload for (project, version), or None."""
    try:
        row = conn.execute(
            "SELECT payload FROM accumulated_cache WHERE project=? AND version=?",
            (project, version),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def write_cached_accumulated(
    conn: sqlite3.Connection, project: str, version: str, payload: dict,
) -> None:
    """Replace the cached accumulated payload for *project* at *version*.

    Single-slot per project: the DELETE clears any prior version first, so the
    table holds at most one accumulated payload per project. The default
    dashboard uses ``as_of=None`` (one version), so this is stable; rapidly
    alternating distinct ``as_of`` historical views would each miss + overwrite.

    Best-effort: logs and returns on any SQLite/serialization error.
    """
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError):
        _logger.warning("accumulated payload for %s not serializable; skipping cache", project)
        return
    try:
        conn.execute("DELETE FROM accumulated_cache WHERE project=?", (project,))
        conn.execute(
            "INSERT OR REPLACE INTO accumulated_cache (project, version, payload) VALUES (?, ?, ?)",
            (project, version, blob),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("accumulated cache write failed for %s", project, exc_info=True)


def read_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str,
) -> dict | None:
    """Return the cached project-card summary for (project, version), or None."""
    try:
        row = conn.execute(
            "SELECT payload FROM project_summary_cache WHERE project=? AND version=?",
            (project, version),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def write_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str, payload: dict,
) -> None:
    """Single-slot-per-project write for the project-card summary."""
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError):
        return
    try:
        conn.execute("DELETE FROM project_summary_cache WHERE project=?", (project,))
        conn.execute(
            "INSERT OR REPLACE INTO project_summary_cache (project, version, payload) VALUES (?, ?, ?)",
            (project, version, blob),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("project summary cache write failed for %s", project, exc_info=True)


def store_run_keys(
    conn: sqlite3.Connection, project: str, run_id: str,
    dismiss_keys: set[tuple], class_keys: set[tuple],
) -> None:
    """Persist a run's key sets (best-effort)."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO run_keys (project, run_id, dismiss_keys, class_keys) "
            "VALUES (?, ?, ?, ?)",
            (project, run_id,
             json.dumps(sorted(list(k) for k in dismiss_keys)),
             json.dumps(sorted(list(k) for k in class_keys))),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("run_keys write failed for %s/%s", project, run_id, exc_info=True)


def load_run_keys(
    conn: sqlite3.Connection, project: str,
) -> dict[str, tuple[set[tuple], set[tuple]]]:
    """Return ``{run_id: (dismiss_keys, class_keys)}`` for *project* (empty on error)."""
    out: dict[str, tuple[set[tuple], set[tuple]]] = {}
    try:
        rows = conn.execute(
            "SELECT run_id, dismiss_keys, class_keys FROM run_keys WHERE project=?",
            (project,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    for run_id, dj, cj in rows:
        try:
            out[run_id] = ({tuple(k) for k in json.loads(dj)},
                           {tuple(k) for k in json.loads(cj)})
        except (ValueError, TypeError):
            continue
    return out


def load_run_keys_or_empty(
    project: str,
) -> dict[str, tuple[set[tuple], set[tuple]]]:
    """Leak-free wrapper: open the cache, load a project's run keys, close.

    Returns {} on any sqlite3 error, including one from ``open_score_cache``
    itself (an unopenable/twice-corrupt db raises past its one rebuild
    attempt), not just from the query — matching every other read in this
    module's empty-on-error contract. Named for the call site in
    ``services.score_cache.per_run_versions``, which used to open the
    connection itself and only wrap the query, letting an open/rebuild
    failure propagate to callers (``scoring.get_project_scores``,
    ``services._fs_metadata`` summaries) that expect this disposable cache
    to degrade to recompute, never raise.
    """
    try:
        with open_score_cache() as conn:
            return load_run_keys(conn, project)
    except sqlite3.Error:
        return {}


def store_run_keys_best_effort(
    project: str, run_id: str,
    dismiss_keys: set[tuple], class_keys: set[tuple],
) -> None:
    """Leak-free wrapper: open the cache, store a run's key sets, close.

    Best-effort: swallows any sqlite3 error, including one from
    ``open_score_cache`` itself, not just from the write (``store_run_keys``
    already logs+returns on a query/serialization error; this also covers
    an open/rebuild failure the same way). Named for the call site in
    ``services.score_cache.per_run_versions`` (see :func:`load_run_keys_or_empty`).
    """
    try:
        with open_score_cache() as conn:
            store_run_keys(conn, project, run_id, dismiss_keys, class_keys)
    except sqlite3.Error:
        _logger.warning("run_keys open failed for %s/%s", project, run_id, exc_info=True)


def read_all_cached_rows(
    conn: sqlite3.Connection, project: str,
) -> dict[tuple[str, str], list[DimensionResult]]:
    """Every cached scalar row for *project*, grouped by (run_id, version).

    Empty dict on any sqlite3.Error (missing table included) -- the caller
    (the bulk-load path in ``services._score_cache_fetch``) treats an empty
    result as "nothing cached yet", not an error.
    """
    by_run_version: dict[tuple[str, str], list[DimensionResult]] = {}
    try:
        rows = conn.execute(
            "SELECT run_id, version, dimension, overall_score, overall_grade "
            "FROM run_scalars WHERE project=? ORDER BY run_id, dimension",
            (project,),
        )
        for rid, ver, dim, score, grade in rows:
            by_run_version.setdefault((rid, ver), []).append(
                DimensionResult(dimension=dim, overall_score=score, overall_grade=grade))
    except sqlite3.Error:
        return {}
    return by_run_version


def read_project_summary_cached(project: str, version: str) -> dict | None:
    """Leak-free wrapper: open the cache, read one project-summary row, close.

    Returns None on any sqlite3 error (corrupt/locked db) as well as a clean
    miss, matching every other read in this module's None-on-miss contract.
    """
    try:
        with open_score_cache() as conn:
            return read_cached_project_summary(conn, project, version)
    except sqlite3.Error:
        return None
