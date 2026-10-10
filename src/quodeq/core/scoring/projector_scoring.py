"""Canonical scoring functions used by the projection engine.

Both this module and services/_rescore_legacy.py (the in-place fallback
behind services/rescore.py) call the same shared primitives in
core/scoring/internals.py, which is why they produce the same numeric
results. Inputs assume dismissed findings have been filtered upstream by
the caller.

Output dicts are the neutral domain result contract; persistence adapters
map them to their own schema (never the other way round):

- principle grade (``compute_principle_grade``):
  ``principle_id``, ``score``, ``grade``, ``finding_count``, ``dismissed_count``,
  ``confidence``, ``observation``
- dimension score (``compute_dimension_score``):
  ``dimension``, ``score``, ``grade``, ``confidence``
- run score (``compute_run_score``):
  ``score``, ``grade``
"""
from __future__ import annotations

from typing import Any

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.run.exit_reason import ExitReason
from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.internals import (
    finding_to_scoring_dict,
    principle_score_and_grade,
    score_to_grade_label,
)
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    dimension_weighted_average,
)
# Also re-exported: callers of the projector import the scale from here.
from quodeq.core.scoring.scale import PrincipleGradeScale
from quodeq.core.types.finding import Finding
from quodeq.core.types.scoring import ConfidenceLevel

# Version of the grade math projected into each run's SQLite grade tables.
# Bump it whenever a change here (or in the scoring internals this module
# calls) alters the numbers an ALREADY-SCANNED run would produce, the
# projector re-derives that run's grades on next contact instead of serving
# the old math forever. Without the stamp, the clamp-order fix (floor no
# longer beats ceiling) left projected runs on the old ordering while fresh
# rescores used the new one: the same principle read 8.0 on one screen and
# 7.3 on another. Same pattern as the ``algo`` salt in services/score_cache.
#
# 1: implicit pre-stamp state (any DB without the run_meta key).
# 2: ceiling beats floor in the principle-score clamp.
# 3: tally groups findings by req before vt (issue #1274).
# 4: requirement spread, standard-owned severity classes, observation-weighted
# 5: the finding's own severity again; the standard only suggests, in the prompt
#    principles, thin evidence scored instead of gated (spec 2026-10-09).
GRADE_ALGO_VERSION = 5

# A dimension is flagged low confidence when more than this share of its
# observation comes from low-confidence principles.
_LOW_CONFIDENCE_SHARE = 0.5


def _insufficient_grade(principle_id: str, finding_count: int, dismissed_count: int) -> dict[str, Any]:
    return {
        "principle_id": principle_id,
        "score": None,
        "grade": Grade.INSUFFICIENT,
        "finding_count": finding_count,
        "dismissed_count": dismissed_count,
        "confidence": None,
        "observation": 0.0,
    }


def compute_principle_grade(
    *,
    principle_id: str,
    findings: list[Finding],
    compliance: list[Finding],
    dismissed_count: int = 0,
    scale: PrincipleGradeScale = PrincipleGradeScale(),
) -> dict[str, Any]:
    """Score a single principle. ``findings`` excludes dismissed.

    Thin evidence is scored and carries ``confidence``; only a principle with
    no findings and no compliance is Insufficient. Returns a principle-grade
    result dict (keys listed in the module docstring).
    """
    if not findings and not compliance:
        return _insufficient_grade(principle_id, 0, dismissed_count)

    confidence = classify_confidence_level(
        len(findings), len(compliance),
        scale_multiplier=scale.scale_multiplier,
        source_file_count=scale.source_file_count,
    )
    rows = requirement_rows(
        [finding_to_scoring_dict(v) for v in findings],
        [finding_to_scoring_dict(c) for c in compliance],
    )
    mass = principle_mass(rows, scale.source_file_count, params=scale.params)
    final, grade = principle_score_and_grade(mass, params=scale.params)
    return {
        "principle_id": principle_id,
        "score": final,
        "grade": grade,
        "finding_count": len(findings),
        "dismissed_count": dismissed_count,
        "confidence": str(confidence),
        "observation": mass.observation,
    }


def compute_dimension_score(
    *,
    dimension: str,
    principle_grades: list[dict[str, Any]],
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Observation-weighted mean of the scored principles into a dimension score.

    Equal weights when no scored principle carries observation. ``confidence``
    is ``"low"`` when more than half the weight is low-confidence, else ``None``.
    Per-dimension weights apply across DIMENSIONS (see ``compute_run_score``).
    """
    scored = [p for p in principle_grades if p.get("score") is not None]
    if not scored:
        return {"dimension": dimension, "score": None, "grade": Grade.INSUFFICIENT, "confidence": None}
    use_observation = any(float(p.get("observation") or 0.0) > 0 for p in scored)
    weights = [float(p.get("observation") or 0.0) if use_observation else 1.0 for p in scored]
    total = sum(weights)
    avg = round(sum(p["score"] * w for p, w in zip(scored, weights)) / total, 1)
    low = sum(w for p, w in zip(scored, weights) if p.get("confidence") == ConfidenceLevel.LOW)
    confidence = str(ConfidenceLevel.LOW) if low > total * _LOW_CONFIDENCE_SHARE else None
    return {
        "dimension": dimension,
        "score": avg,
        "grade": score_to_grade_label(avg, params=params),
        "confidence": confidence,
    }


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
        if d.get("score") is not None and d.get("exit_reason") != ExitReason.FAILURE_STREAK
    ]
    avg = dimension_weighted_average(pairs, params)
    if avg is None:
        return {"score": None, "grade": None}
    return {"score": avg, "grade": score_to_grade_label(avg, params=params)}
