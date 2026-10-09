"""Turn the SQL grade rows of a run into sorted :class:`DimensionResult` values.

The scalar fast path in :mod:`runs` reads these rows instead of the evaluation
JSON; this module is the shape conversion only.
"""
from __future__ import annotations

from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import SeverityTally, Totals
from quodeq.data.sqlite.dimension_counts import DimensionCounts


def scalars_to_dimension_results(
    dim_rows: list[dict], principle_rows: list[dict],
    counts: dict[str, DimensionCounts] | None = None,
    metadata: dict | None = None,
) -> list[DimensionResult]:
    """Build sorted DimensionResults from validated SQL grade rows.

    No eval-time grade fallback here (unlike overlay_sql_grades): the fast
    path doesn't read the JSON, and a projected dim past the NULL-score
    guard always carries a real grade label ("Insufficient" or better),
    never "". *metadata* is the run-level manifest part a full read attaches
    (``sourceFileCount``, ``discipline``); the exit reason comes from the row.
    """
    from quodeq.core.types.report import PrincipleGrade  # noqa: PLC0415

    meta = metadata or {}

    principles_by_dim: dict[str, list[PrincipleGrade]] = {}
    for r in principle_rows:
        principles_by_dim.setdefault(r["dimension"], []).append(PrincipleGrade(
            principle=r["principle_id"],
            score=f'{r["score"]}/10' if r.get("score") is not None else None,
            grade=r.get("grade"),
            confidence=r.get("confidence"),
        ))

    dimensions = [
        DimensionResult(
            dimension=r["dimension"],
            overall_score=f'{r["score"]}/10',
            overall_grade=r.get("grade"),
            principles=principles_by_dim.get(r["dimension"], []),
            files_read=r.get("files_read"),
            exit_reason=r.get("exit_reason"),
            confidence=r.get("confidence"),
            source_file_count=meta.get("sourceFileCount"),
            discipline=meta.get("discipline"),
            **_scalar_counts((counts or {}).get(r["dimension"])),
        )
        for r in dim_rows
    ]
    dimensions.sort(key=lambda d: d.dimension)
    return dimensions


def _scalar_counts(c: "DimensionCounts | None") -> dict:
    """``totals`` and ``open_types`` for a scalar dimension, or nothing when unknown."""
    if c is None:
        return {}
    tally = SeverityTally(critical=c.critical, major=c.major, minor=c.minor)
    return {
        "totals": Totals(violation_count=c.violations, compliance_count=c.compliance, severity=tally),
        "open_types": c.open_types,
    }
