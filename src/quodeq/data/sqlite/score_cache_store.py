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
from dataclasses import dataclass

from quodeq.core.types import DimensionResult
from quodeq.data.sqlite.score_cache_db import open_score_cache
from quodeq.data.sqlite.score_cache_principles import (
    attach_principles, principle_rows, read_principle_rows, write_principle_rows,
)
from quodeq.data.sqlite.score_cache_rows import RUN_SCALARS_COLUMNS, dimension_from_row, row_values

_logger = logging.getLogger(__name__)

_SCALAR_COLUMNS = ", ".join(RUN_SCALARS_COLUMNS)
_SCALAR_PLACEHOLDERS = ", ".join("?" * len(RUN_SCALARS_COLUMNS))


def read_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
) -> list[DimensionResult] | None:
    """The run's row dimensions at *version*, principles attached; None on miss or error."""
    try:
        rows = conn.execute(
            f"SELECT {_SCALAR_COLUMNS} FROM run_scalars"
            " WHERE project=? AND run_id=? AND version=? ORDER BY dimension",
            (project, run_id, version),
        ).fetchall()
        principles = read_principle_rows(conn, project, run_id) if rows else {}
    except sqlite3.Error:
        return None
    if not rows:
        return None
    return attach_principles([dimension_from_row(r) for r in rows], principles.get((run_id, version), {}))


def write_cached_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str,
    dims: list[DimensionResult],
) -> None:
    """Replace all cached rows for (project, run_id) with *dims* at *version*.

    Each dimension's scalars go to ``run_scalars`` and its principle grades to
    ``run_principle_scalars``, in one commit. Best-effort: logs and returns on
    any SQLite error (the caller still has the computed result).
    """
    try:
        conn.execute("DELETE FROM run_scalars WHERE project=? AND run_id=?", (project, run_id))
        write_principle_rows(conn, project, run_id, version, principle_rows(dims))
        conn.executemany(
            f"INSERT OR REPLACE INTO run_scalars (project, run_id, version, {_SCALAR_COLUMNS})"
            f" VALUES (?, ?, ?, {_SCALAR_PLACEHOLDERS})",
            [(project, run_id, version, *row_values(d)) for d in dims if d.dimension],
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning("score cache write failed for %s/%s", project, run_id, exc_info=True)


@dataclass(frozen=True)
class _PayloadSlot:
    """One single-slot-per-project JSON payload table and the warnings it logs."""

    table: str  # a module constant below, never caller input (it is formatted into the SQL)
    write_failed_log: str  # %s is the project


_PROJECT_SUMMARY = _PayloadSlot("project_summary_cache", "project summary cache write failed for %s")


def _load_payload(conn: sqlite3.Connection, sql: str, params: tuple) -> dict | None:
    """The JSON payload of the first row *sql* selects; None on miss, error or bad JSON."""
    try:
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None


def _read_payload(conn: sqlite3.Connection, slot: _PayloadSlot, project: str, version: str) -> dict | None:
    """The payload stored in *slot* for (project, version); None on miss, error or bad JSON."""
    return _load_payload(
        conn, f"SELECT payload FROM {slot.table} WHERE project=? AND version=?", (project, version),
    )


def _write_payload(
    conn: sqlite3.Connection, slot: _PayloadSlot, project: str, version: str, payload: dict,
) -> None:
    """Replace *project*'s payload in *slot* with *payload* at *version* (best-effort)."""
    try:
        blob = json.dumps(payload)
    except (TypeError, ValueError):
        return
    try:
        conn.execute(f"DELETE FROM {slot.table} WHERE project=?", (project,))
        conn.execute(
            f"INSERT OR REPLACE INTO {slot.table} (project, version, payload) VALUES (?, ?, ?)",
            (project, version, blob),
        )
        conn.commit()
    except sqlite3.Error:
        _logger.warning(slot.write_failed_log, project, exc_info=True)


def read_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str,
) -> dict | None:
    """Return the cached project-card summary for (project, version), or None."""
    return _read_payload(conn, _PROJECT_SUMMARY, project, version)


def write_cached_project_summary(
    conn: sqlite3.Connection, project: str, version: str, payload: dict,
) -> None:
    """Single-slot-per-project write for the project-card summary.

    Best-effort: logs a SQLite error; an unserializable payload is skipped silently.
    """
    _write_payload(conn, _PROJECT_SUMMARY, project, version, payload)


def store_run_keys(
    conn: sqlite3.Connection, project: str, run_id: str,
    dismiss_keys: set[tuple], class_keys: set[tuple],
) -> None:
    """Persist a run's key sets (best-effort)."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO run_keys (project, run_id, dismiss_keys, class_keys) "
            "VALUES (?, ?, ?, ?)",
            (project, run_id, _keys_json(dismiss_keys), _keys_json(class_keys)),
        )
        conn.commit()
    except (sqlite3.Error, TypeError, ValueError):
        _logger.warning("run_keys write failed for %s/%s", project, run_id, exc_info=True)


def _keys_json(keys: set[tuple]) -> str:
    """JSON array of *keys*, in a deterministic order.

    Ordered by each key's JSON form rather than by element comparison: a
    dismiss key ends in an int line or a str fingerprint for the same finding
    (``finding_dismiss_keys``), and Python refuses to order an int against a
    str. ``load_run_key_sets`` rebuilds a set, so only determinism matters here.
    """
    return json.dumps(sorted((list(k) for k in keys), key=json.dumps))


def load_run_key_sets(
    conn: sqlite3.Connection, project: str, run_id: str,
) -> tuple[set[tuple], set[tuple]] | None:
    """One run's persisted ``(dismiss_keys, class_keys)``; None when absent or unreadable.

    A single primary-key row, decoded on demand. A large project's blobs run
    to megabytes per run, so the per-run paths (trend fetch, scoped versions)
    must never decode the whole table to answer for one run.
    """
    try:
        row = conn.execute(
            "SELECT dismiss_keys, class_keys FROM run_keys WHERE project=? AND run_id=?",
            (project, run_id),
        ).fetchone()
    except sqlite3.Error:
        return None
    return _decode_keys(*row) if row else None


def _decode_keys(dj: str, cj: str) -> tuple[set[tuple], set[tuple]] | None:
    try:
        return ({tuple(k) for k in json.loads(dj)}, {tuple(k) for k in json.loads(cj)})
    except (ValueError, TypeError):
        return None


def read_all_cached_rows(
    conn: sqlite3.Connection, project: str,
) -> dict[tuple[str, str], list[DimensionResult]]:
    """Every cached row dimension of *project*, principles attached, grouped by (run_id, version).

    Empty dict on any sqlite3.Error (missing table included) -- the caller
    (the bulk-load path in ``services._score_cache_fetch``) treats an empty
    result as "nothing cached yet", not an error.
    """
    by_run_version: dict[tuple[str, str], list[DimensionResult]] = {}
    try:
        rows = conn.execute(
            f"SELECT run_id, version, {_SCALAR_COLUMNS} FROM run_scalars"
            " WHERE project=? ORDER BY run_id, dimension",
            (project,),
        )
        for rid, ver, *row in rows:
            by_run_version.setdefault((rid, ver), []).append(dimension_from_row(tuple(row)))
        principles = read_principle_rows(conn, project)
    except sqlite3.Error:
        return {}
    return {key: attach_principles(dims, principles.get(key, {})) for key, dims in by_run_version.items()}


def read_last_project_summary(conn: sqlite3.Connection, project: str) -> dict | None:
    """The project-card summary row whatever version it was computed under.

    The table keeps one row per project, so after a version change (new
    formula, upgrade) the previous summary is still here until the warm-up
    rewrites it. That is the last known grade a pending card or Overview can
    show while the rebuild runs. None on miss, error or bad JSON.
    """
    return _load_payload(
        conn, f"SELECT payload FROM {_PROJECT_SUMMARY.table} WHERE project=?", (project,),
    )


def read_last_project_summary_cached(project: str) -> dict | None:
    """Open the cache, read the project's last summary row whatever its version, close.

    None on a clean miss and on any sqlite3 error (corrupt/locked db).
    """
    try:
        with open_score_cache() as conn:
            return read_last_project_summary(conn, project)
    except sqlite3.Error:
        return None


def read_project_summary_or_last(project: str, version: str) -> tuple[dict | None, bool]:
    """``(summary, settled)`` in one cache open: the row at *version*, else the last known row.

    ``settled`` is True only for the exact-version hit. A last known row is
    the previous version's summary, for showing while the rebuild runs; no
    row at all answers ``(None, False)``. One connection for both reads, so
    a cold project list pays one open per card, as it did before the last
    known row was consulted.
    """
    try:
        with open_score_cache() as conn:
            hit = read_cached_project_summary(conn, project, version)
            if hit is not None:
                return hit, True
            return read_last_project_summary(conn, project), False
    except sqlite3.Error:
        return None, False
