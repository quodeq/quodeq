"""Scoring formula functions and re-exports for backward compatibility."""
from __future__ import annotations

import math
from typing import Any

from quodeq.core.scoring.constants import (  # noqa: F401 — re-exports
    GRADE_LADDER,
    MAX_SCORE,
    SCALE_TIER_NAMES,
    MAX_PENALTY_MULTIPLIER,
    RATIO_DAMPENING_TABLE,
    SCALE_TIERS,
    SEVERITY_WEIGHT,
    WEIGHT_DOUBLE,
    WEIGHT_TRIPLE,
    scale_multiplier,
)
from quodeq.core.scoring._tallies import (  # noqa: F401 — re-exports
    weighted_sum,
    evidence_has_taxonomy,
    tally_types,
)
from quodeq.core.scoring.confidence import confidence_interval_for  # noqa: F401 — re-export
from quodeq.core.scoring.numerical import (  # noqa: F401 — re-export
    build_deductions,
    count_grade_drops,
)
from quodeq.core.scoring.mass import PrincipleMass
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.finding import Finding
from quodeq.core.types.severity import Severity


# ---------------------------------------------------------------------------
# 4-stage scoring formula, on requirement masses (core/scoring/mass.py)
# ---------------------------------------------------------------------------

def violation_base(violation_mass: float, *, params: ScoringParams = DEFAULT_PARAMS) -> float:
    """``base = 10 / (1 + K · violation_mass)``; 10 with no violations."""
    if violation_mass <= 0:
        return float(MAX_SCORE)
    return MAX_SCORE / (1.0 + params.base_k * violation_mass)


def compliance_lift(
    compliance_mass: float, violation_mass: float, *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Fraction of the gap to 10 that compliance fills: ``(cc / (cc + wv)) ^ compress``."""
    if compliance_mass <= 0 or violation_mass <= 0:
        return 0.0
    return (compliance_mass / (compliance_mass + violation_mass)) ** params.lift_compress


def violation_ceiling(violation_mass: float, *, params: ScoringParams = DEFAULT_PARAMS) -> float:
    """``ceiling = 10 − scale · log2(1 + violation_mass)``."""
    if violation_mass <= 0:
        return float(MAX_SCORE)
    return MAX_SCORE - math.log2(1.0 + violation_mass) * params.ceil_scale


def severity_grade_floor(worst: str | None, *, params: ScoringParams = DEFAULT_PARAMS) -> float:
    """The lowest score the worst effective severity allows; 10 with no violations."""
    if worst == Severity.CRITICAL:
        return 0.0
    if worst == Severity.MAJOR:
        return params.floor_major
    if worst == Severity.MINOR:
        return params.floor_minor
    return float(MAX_SCORE)


def finding_to_scoring_dict(f: Finding) -> dict[str, Any]:
    """The dict shape the mass builder reads: severity, reason, req, vt and file."""
    d: dict[str, Any] = {"severity": f.severity or Severity.MINOR, "reason": f.reason or ""}
    if f.req:
        d["req"] = f.req
    if f.violation_type:
        d["vt"] = f.violation_type
    if f.file:
        d["file"] = f.file
    return d


def clamp_principle_score(
    raw: float, violation_mass: float, worst: str | None, *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Floor first, ceiling last: the ceiling (volume) wins when the two cross."""
    ceil = violation_ceiling(violation_mass, params=params)
    floor = severity_grade_floor(worst, params=params)
    return round(min(ceil, max(floor, raw)), 1)


def principle_stages(
    mass: PrincipleMass, *, params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float, float, float, float]:
    """``(base, lift, raw, final)`` for one principle's masses."""
    base = violation_base(mass.violation_mass, params=params)
    lift = compliance_lift(mass.compliance_mass, mass.violation_mass, params=params)
    raw = base + (MAX_SCORE - base) * lift
    final = clamp_principle_score(raw, mass.violation_mass, mass.worst, params=params)
    return base, lift, raw, final


def principle_score_and_grade(
    mass: PrincipleMass, *, params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float, str]:
    """Score one principle from its masses. Returns (score, grade_label)."""
    _base, _lift, _raw, final = principle_stages(mass, params=params)
    return final, score_to_grade_label(final, params=params)


# ---------------------------------------------------------------------------
# Grade and legacy helpers
# ---------------------------------------------------------------------------

def score_to_grade_label(
    score: float, *, params: ScoringParams = DEFAULT_PARAMS,
) -> str:
    """Convert a 0-10 numerical score to a descriptive grade label."""
    for threshold, label in params.grade_thresholds:
        if score >= threshold:
            return label
    return "Critical"


def compliance_dampening(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Legacy dampening multiplier for the non-numerical (graded) mode."""
    weighted_compliance = weighted_sum(compliance_type_counts)
    weighted_violations = weighted_sum(violation_type_counts)

    if weighted_violations == 0:
        return 1.0
    if weighted_compliance == 0:
        return MAX_PENALTY_MULTIPLIER

    ratio = weighted_compliance / weighted_violations
    for threshold, multiplier in RATIO_DAMPENING_TABLE:
        if ratio >= threshold:
            return multiplier
    return MAX_PENALTY_MULTIPLIER


def drop_grade(grade: str, drops: int) -> str:
    """Reduce a grade by the requested number of levels, flooring at Insufficient."""
    try:
        position = GRADE_LADDER.index(grade)
    except ValueError:
        return GRADE_LADDER[0]
    new_position = max(0, position - drops)
    return GRADE_LADDER[new_position]


_MULTIPLIER_TRIPLE = 3  # the "x3" of WEIGHT_TRIPLE, spelled out
_MULTIPLIER_DOUBLE = 2  # the "x2" of WEIGHT_DOUBLE, spelled out


def weight_as_multiplier(weight_str: str) -> int:
    """Extract the integer multiplier from a weight label like 'High (x3)'."""
    if WEIGHT_TRIPLE in weight_str:
        return _MULTIPLIER_TRIPLE
    if WEIGHT_DOUBLE in weight_str:
        return _MULTIPLIER_DOUBLE
    return 1
