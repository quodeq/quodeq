"""Overlay SQL grade tables onto eval-time DimensionResults.

The event-log scoring engine bakes per-run grades into ``evaluation.db``
(``dimension_scores`` + ``principle_grades``).  Those tables are the source of
truth once a run has an ``events.jsonl`` — they are rewritten by
``data.projection.grade_projector.recompute_grades`` whenever the user dismisses
a finding *or* applies a custom grade formula.

The eval-time ``evaluation/<dim>.json`` files, by contrast, are frozen at the
moment the CLI wrote them.  After an Apply they are stale.  This module overlays
the SQL grades onto the ``DimensionResult`` objects parsed from those JSON files
so every read-side consumer (run detail, accumulated overview, trend, project
cards) sees the same numbers by construction.

Legacy runs (no ``events.jsonl`` → empty grade tables) keep their eval-time
grades untouched — correct, because they cannot be rescored.

Robustness: a run whose ``evaluation.db`` is unreadable (written by a newer
Quodeq, or half-written) must not crash the dashboard.  All SQLite access is
wrapped so a ``DatabaseError`` falls back to the eval-time grades, mirroring
``get_scores_raw``.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.core.types.report import PrincipleGrade

_logger = logging.getLogger(__name__)


def _overlay_principles(
    existing: list[PrincipleGrade], sql_rows: list[dict],
) -> list[PrincipleGrade]:
    """Return principle grades with SQL score/grade applied by principle id.

    Principles present in the eval-time JSON but absent from SQL keep their
    eval-time values (e.g. an Insufficient principle the projector dropped).
    SQL is matched on ``principle_id`` against the JSON principle's name.
    """
    if not sql_rows:
        return existing
    by_id = {r["principle_id"]: r for r in sql_rows}
    overlaid: list[PrincipleGrade] = []
    for p in existing:
        row = by_id.get(p.principle)
        if row is None:
            overlaid.append(p)
            continue
        score_val = row.get("score")
        overlaid.append(replace(
            p,
            score=f"{score_val}/10" if score_val is not None else p.score,
            grade=row.get("grade") or p.grade,
        ))
    return overlaid


def overlay_sql_grades(
    run_dir: Path, dimensions: list[DimensionResult],
) -> list[DimensionResult]:
    """Overlay SQL ``dimension_scores`` / ``principle_grades`` onto *dimensions*.

    No-op (returns *dimensions* unchanged) when:
      - the run has no ``events.jsonl`` (legacy run — eval-time grades stand),
      - the SQL grade tables are empty (run not yet projected),
      - ``evaluation.db`` is unreadable (newer schema / corruption).

    Per-dimension, only the grade fields are overlaid (``overall_score``,
    ``overall_grade``, and each principle's ``score``/``grade``).  Violations,
    compliance, totals, and trend metadata are left to the eval-time JSON and
    the downstream dismissal filters — this helper changes *grades only*, so it
    is safe to call at the run-read boundary before any aggregation.
    """
    if not dimensions:
        return dimensions
    if not (run_dir / "events.jsonl").is_file():
        return dimensions

    import sqlite3  # noqa: PLC0415

    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415

    store = SQLiteStateStore(run_dir)
    try:
        # Project any pending events first so a freshly-completed run has its
        # grade tables baked before we read them (matches the explorer detail
        # path). ensure_projected is a fast no-op once the log size is stable.
        SqliteFindingsRepository(run_dir)._ensure_fresh()  # noqa: SLF001
        dim_rows = store.read_dimension_scores()
        principle_rows = store.read_principle_grades()
    except sqlite3.DatabaseError:
        _logger.warning(
            "evaluation.db at %s is unreadable; keeping eval-time grades.", run_dir,
        )
        return dimensions
    if not dim_rows:
        return dimensions

    sql_by_dim = {r["dimension"]: r for r in dim_rows}
    principles_by_dim: dict[str, list[dict]] = {}
    for r in principle_rows:
        principles_by_dim.setdefault(r["dimension"], []).append(r)

    overlaid: list[DimensionResult] = []
    for d in dimensions:
        row = sql_by_dim.get(d.dimension)
        if row is None:
            overlaid.append(d)
            continue
        score_val = row.get("score")
        overlaid.append(replace(
            d,
            overall_score=f"{score_val}/10" if score_val is not None else d.overall_score,
            overall_grade=row.get("grade") or d.overall_grade,
            principles=_overlay_principles(d.principles, principles_by_dim.get(d.dimension, [])),
        ))
    return overlaid
