"""Reads and writes of ``run_principle_scalars``, the per-principle companion of ``run_scalars``.

One row per (project, run, version, dimension, principle) with the principle's
score, grade and thin-evidence marker, written and deleted together with the run's ``run_scalars``
rows so a hit on either version carries both. The store attaches them to the
row dimensions it reads; the trend's served shape drops them again
(``score_cache_rows.scalar_dimension``).
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace

from quodeq.core.types import DimensionResult
from quodeq.core.types.report import PrincipleGrade

#: One row to write: ``(dimension, principle, score, grade, confidence)``.
PrincipleRow = tuple[str, str, str | None, str | None, str | None]


def principle_rows(dims: list[DimensionResult]) -> list[PrincipleRow]:
    """The principle rows of *dims*, skipping unnamed principles and dimensions."""
    return [(d.dimension, p.principle, p.score, p.grade, p.confidence)
            for d in dims if d.dimension for p in d.principles if p.principle]


def write_principle_rows(
    conn: sqlite3.Connection, project: str, run_id: str, version: str, rows: list[PrincipleRow],
) -> None:
    """Replace the run's principle rows with *rows* at *version*. Does not commit."""
    conn.execute("DELETE FROM run_principle_scalars WHERE project=? AND run_id=?", (project, run_id))
    conn.executemany(
        "INSERT OR REPLACE INTO run_principle_scalars"
        " (project, run_id, version, dimension, principle, score, grade, confidence)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(project, run_id, version, *row) for row in rows],
    )


#: Principle grades per dimension, keyed by (run_id, version).
PrinciplesByKey = dict[tuple[str, str], dict[str, list[PrincipleGrade]]]


def read_principle_rows(
    conn: sqlite3.Connection, project: str, run_id: str | None = None,
) -> PrinciplesByKey:
    """The project's (or one run's) principle grades, keyed by (run_id, version) then dimension.

    Raises ``sqlite3.Error`` like any other read; the store's callers already
    degrade on it.
    """
    sql = ("SELECT run_id, version, dimension, principle, score, grade, confidence"
           " FROM run_principle_scalars"
           " WHERE project=?")
    args: tuple = (project,)
    if run_id is not None:
        sql, args = sql + " AND run_id=?", (project, run_id)
    out: PrinciplesByKey = {}
    for rid, ver, dim, principle, score, grade, confidence in conn.execute(sql + " ORDER BY rowid", args):
        out.setdefault((rid, ver), {}).setdefault(dim, []).append(
            PrincipleGrade(principle=principle, score=score, grade=grade, confidence=confidence))
    return out


def attach_principles(
    dims: list[DimensionResult], by_dimension: dict[str, list[PrincipleGrade]],
) -> list[DimensionResult]:
    """*dims* each carrying its principle grades from *by_dimension* (none when absent)."""
    return [replace(d, principles=list(by_dimension.get(d.dimension, ()))) for d in dims]
