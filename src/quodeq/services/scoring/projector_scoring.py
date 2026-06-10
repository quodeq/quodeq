"""Canonical scoring functions used by the projection engine.

These produce the same numeric results as services/rescore.py because they
call the same scoring primitives. Inputs assume dismissed findings have been
filtered upstream (the projector reads ``WHERE verdict != 'dismissed'`` from SQL).

Output dicts match the row shape expected by SQLiteStateStore writers.
"""
from __future__ import annotations

from typing import Any

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.engine import compute_tallies
from quodeq.core.scoring.internals import (
    compliance_lift,
    score_to_grade_label,
    severity_grade_floor,
    violation_base,
    violation_ceiling,
)
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    dimension_weighted_average,
)
from quodeq.core.types.finding import Finding


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Convert Finding to the dict shape scoring internals expect.

    Same as the helper in services/rescore.py -- keep them byte-identical.
    Including 'vt' only when violation_type is set preserves the
    taxonomy-vs-reason mode selection.
    """
    d: dict[str, Any] = {
        "severity": f.severity or "minor",
        "reason": f.reason or "",
    }
    if f.violation_type:
        d["vt"] = f.violation_type
    return d


def compute_principle_grade(
    *,
    principle_id: str,
    findings: list[Finding],
    compliance: list[Finding],
    dismissed_count: int = 0,
    source_file_count: int = 0,
    scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Score a single principle. ``findings`` excludes dismissed.

    Mirrors the CLI's ``core/scoring/_principle._score_numerical``: low
    confidence (thin evidence relative to project size) short-circuits to
    ``Insufficient`` before any scoring math runs. Without this gate,
    principles with one or two findings scored ``10.0/Exemplary`` here
    but ``Insufficient`` in the CLI's evaluation JSON — and the
    dashboard's overlaid SQL grades drifted away from the CLI's report.

    Returns a dict suitable for SQLiteStateStore.record_principle_grade.
    """
    if not findings and not compliance:
        return {
            "principle_id": principle_id,
            "score": None,
            "grade": "Insufficient",
            "finding_count": 0,
            "dismissed_count": dismissed_count,
        }

    confidence_level = classify_confidence_level(
        len(findings), len(compliance),
        scale_multiplier=scale_multiplier,
        source_file_count=source_file_count,
    )
    if confidence_level == "low":
        return {
            "principle_id": principle_id,
            "score": None,
            "grade": "Insufficient",
            "finding_count": len(findings),
            "dismissed_count": dismissed_count,
        }

    v_dicts = [_finding_to_dict(v) for v in findings]
    c_dicts = [_finding_to_dict(c) for c in compliance]
    vt_counts, ct_counts, _ = compute_tallies(v_dicts, c_dicts)

    if not any(vt_counts.values()) and not any(ct_counts.values()):
        return {
            "principle_id": principle_id,
            "score": None,
            "grade": "Insufficient",
            "finding_count": len(findings),
            "dismissed_count": dismissed_count,
        }

    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)

    return {
        "principle_id": principle_id,
        "score": final,
        "grade": grade,
        "finding_count": len(findings),
        "dismissed_count": dismissed_count,
    }


def compute_dimension_score(
    *,
    dimension: str,
    principle_grades: list[dict[str, Any]],
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Average non-Insufficient principle scores into a dimension-level score.

    Averaging across PRINCIPLES is always a plain mean; per-dimension weights
    apply across DIMENSIONS (see ``compute_run_score``), not principles.
    """
    scored = [p for p in principle_grades if p.get("score") is not None]
    if not scored:
        return {"dimension": dimension, "score": None, "grade": "Insufficient"}
    avg = round(sum(p["score"] for p in scored) / len(scored), 1)
    return {"dimension": dimension, "score": avg, "grade": score_to_grade_label(avg, params=params)}


def compute_run_score(
    dimension_scores: list[dict[str, Any]],
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Average non-null dimension scores into a run-level score.

    Applies per-dimension weights when params enable them.
    """
    pairs = [
        (d.get("dimension"), d["score"])
        for d in dimension_scores if d.get("score") is not None
    ]
    avg = dimension_weighted_average(pairs, params)
    if avg is None:
        return {"score": None, "grade": None}
    return {"score": avg, "grade": score_to_grade_label(avg, params=params)}
