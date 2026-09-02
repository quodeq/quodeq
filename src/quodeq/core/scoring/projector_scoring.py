"""Canonical scoring functions used by the projection engine.

These produce the same numeric results as services/rescore.py because they
call the same scoring primitives. Inputs assume dismissed findings have been
filtered upstream by the caller.

Output dicts are the neutral domain result contract; persistence adapters
map them to their own schema (never the other way round):

- principle grade (``compute_principle_grade``):
  ``principle_id``, ``score``, ``grade``, ``finding_count``, ``dismissed_count``
- dimension score (``compute_dimension_score``):
  ``dimension``, ``score``, ``grade``
- run score (``compute_run_score``):
  ``score``, ``grade``
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

# Version of the grade math projected into each run's SQLite grade tables.
# Bump it whenever a change here (or in the scoring internals this module
# calls) alters the numbers an ALREADY-SCANNED run would produce — the
# projector re-derives that run's grades on next contact instead of serving
# the old math forever. Without the stamp, the clamp-order fix (floor no
# longer beats ceiling) left projected runs on the old ordering while fresh
# rescores used the new one: the same principle read 8.0 on one screen and
# 7.3 on another. Same pattern as the ``algo`` salt in services/score_cache.
#
# 1: implicit pre-stamp state (any DB without the run_meta key).
# 2: ceiling beats floor in the principle-score clamp.
GRADE_ALGO_VERSION = 2


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


def _insufficient_grade(principle_id: str, finding_count: int, dismissed_count: int) -> dict[str, Any]:
    return {
        "principle_id": principle_id,
        "score": None,
        "grade": "Insufficient",
        "finding_count": finding_count,
        "dismissed_count": dismissed_count,
    }


def _score_principle_math(vt_counts, ct_counts, params: ScoringParams) -> tuple[float, str]:
    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    # Floor first, ceiling last. The two guards cross when a principle carries a
    # LOT of issues that all happen to be minor: the minor-only floor (8.0) rises
    # above the volume ceiling. Clamping the other way round handed back the
    # floor and discarded the ceiling -- the one guard that encodes volume -- so
    # a principle with 269 findings read "Good". Algebraically identical whenever
    # floor <= ceil, so only the contradictory case moves.
    # Keep byte-identical with services/rescore.py.
    final = min(ceil, max(floor, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    return final, grade


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

    Returns a principle-grade result dict (keys listed in the module
    docstring).
    """
    if not findings and not compliance:
        return _insufficient_grade(principle_id, 0, dismissed_count)

    confidence_level = classify_confidence_level(
        len(findings), len(compliance),
        scale_multiplier=scale_multiplier,
        source_file_count=source_file_count,
    )
    if confidence_level == "low":
        return _insufficient_grade(principle_id, len(findings), dismissed_count)

    v_dicts = [_finding_to_dict(v) for v in findings]
    c_dicts = [_finding_to_dict(c) for c in compliance]
    vt_counts, ct_counts, _ = compute_tallies(v_dicts, c_dicts)

    if not any(vt_counts.values()) and not any(ct_counts.values()):
        return _insufficient_grade(principle_id, len(findings), dismissed_count)

    final, grade = _score_principle_math(vt_counts, ct_counts, params)

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
    # Dimensions aborted by the failure-streak circuit breaker carry a
    # provisional, structurally-optimistic score (the errored files are the
    # ones with no findings). Show the per-dim score but keep it OUT of the
    # overall grade. time_limit and other partial reasons still count.
    pairs = [
        (d.get("dimension"), d["score"])
        for d in dimension_scores
        if d.get("score") is not None and d.get("exit_reason") != "failure_streak"
    ]
    avg = dimension_weighted_average(pairs, params)
    if avg is None:
        return {"score": None, "grade": None}
    return {"score": avg, "grade": score_to_grade_label(avg, params=params)}
