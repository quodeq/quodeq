"""Scoring formula functions and re-exports for backward compatibility."""
from __future__ import annotations

import math
from typing import Any

from quodeq.core.scoring._constants import (  # noqa: F401 — re-exports
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    _MAX_PENALTY_MULTIPLIER,
    _RATIO_DAMPENING_TABLE,
    _SCALE_TIERS,
    _SEVERITY_WEIGHT,
    _WEIGHT_DOUBLE,
    _WEIGHT_TRIPLE,
    scale_multiplier,
)
from quodeq.core.scoring._tallies import (  # noqa: F401 — re-exports
    _weighted_sum,
    evidence_has_taxonomy,
    tally_types,
)
from quodeq.core.scoring.confidence import confidence_interval_for  # noqa: F401 — re-export
from quodeq.core.scoring.numerical import (  # noqa: F401 — re-export
    build_deductions,
    count_grade_drops,
)
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.finding import Finding


# ---------------------------------------------------------------------------
# 4-stage scoring formula
# ---------------------------------------------------------------------------

def violation_base(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the base score from violations alone (ignoring compliance).

    Uses a hyperbolic curve: ``base = 10 / (1 + K * weighted_violations)``
    Returns a value in [0, 10].
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    if wv == 0:
        return 10.0
    return 10.0 / (1.0 + params.base_k * wv)


def compliance_lift(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the lift factor from compliance evidence.

    Returns a value in [0, 1] representing the fraction of the gap filled.
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    cc = sum(compliance_type_counts.get(sev, 0) for sev in compliance_type_counts)
    if cc == 0 or wv == 0:
        return 0.0
    raw_lift = cc / (cc + wv)
    return raw_lift ** params.lift_compress


def violation_ceiling(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the maximum achievable score given the violation weight.

    ``ceiling = 10 - log2(1 + wv) * CEIL_SCALE``
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    if wv == 0:
        return 10.0
    return 10.0 - math.log2(1.0 + wv) * params.ceil_scale


def severity_grade_floor(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Return the minimum score based on the worst violation severity present."""
    if violation_type_counts.get("critical", 0) > 0:
        return 0.0
    if violation_type_counts.get("major", 0) > 0:
        return params.floor_major
    if violation_type_counts.get("minor", 0) > 0:
        return params.floor_minor
    return 10.0


def finding_to_scoring_dict(f: Finding) -> dict[str, Any]:
    """Convert a Finding dataclass to the dict format scoring internals expect.

    Only includes 'vt' when the finding has an explicit violation_type, so
    ``evidence_has_taxonomy()`` selects the same mode (taxonomy vs reason)
    that the original evaluation used.
    """
    d: dict[str, Any] = {
        "severity": f.severity or "minor",
        "reason": f.reason or "",
    }
    if f.violation_type:
        d["vt"] = f.violation_type
    return d


def principle_score_and_grade(
    vt_counts: dict[str, int],
    ct_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float, str]:
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
    final = min(ceil, max(floor, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    return final, grade


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
    weighted_compliance = _weighted_sum(compliance_type_counts)
    weighted_violations = _weighted_sum(violation_type_counts)

    if weighted_violations == 0:
        return 1.0
    if weighted_compliance == 0:
        return _MAX_PENALTY_MULTIPLIER

    ratio = weighted_compliance / weighted_violations
    for threshold, multiplier in _RATIO_DAMPENING_TABLE:
        if ratio >= threshold:
            return multiplier
    return _MAX_PENALTY_MULTIPLIER


def drop_grade(grade: str, drops: int) -> str:
    """Reduce a grade by the requested number of levels, flooring at Insufficient."""
    try:
        position = GRADE_LADDER.index(grade)
    except ValueError:
        return GRADE_LADDER[0]
    new_position = max(0, position - drops)
    return GRADE_LADDER[new_position]


def weight_as_multiplier(weight_str: str) -> int:
    """Extract the integer multiplier from a weight label like 'High (x3)'."""
    if _WEIGHT_TRIPLE in weight_str:
        return 3
    if _WEIGHT_DOUBLE in weight_str:
        return 2
    return 1
