"""Scoring formula functions and re-exports for backward compatibility."""
from __future__ import annotations

import math

from quodeq.core.scoring._constants import *  # noqa: F401,F403
from quodeq.core.scoring._constants import (
    _BASE_K,
    _CEIL_SCALE,
    _GRADE_THRESHOLDS,
    _LIFT_COMPRESS,
    _MAX_PENALTY_MULTIPLIER,
    _RATIO_DAMPENING_TABLE,
    _SEVERITY_GRADE_FLOOR,
    _WEIGHT_DOUBLE,
    _WEIGHT_TRIPLE,
    GRADE_LADDER,
)
from quodeq.core.scoring._tallies import *  # noqa: F401,F403
from quodeq.core.scoring._tallies import _weighted_sum
from quodeq.core.scoring.confidence import confidence_interval_for  # noqa: F401 — re-export
from quodeq.core.scoring.numerical import (  # noqa: F401 — re-export
    build_deductions,
    count_grade_drops,
)


# ---------------------------------------------------------------------------
# 4-stage scoring formula
# ---------------------------------------------------------------------------

def violation_base(violation_type_counts: dict[str, int]) -> float:
    """Compute the base score from violations alone (ignoring compliance).

    Uses a hyperbolic curve: ``base = 10 / (1 + K * weighted_violations)``
    Returns a value in [0, 10].
    """
    wv = _weighted_sum(violation_type_counts)
    if wv == 0:
        return 10.0
    return 10.0 / (1.0 + _BASE_K * wv)


def compliance_lift(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Compute the lift factor from compliance evidence.

    Returns a value in [0, 1] representing the fraction of the gap filled.
    """
    wv = _weighted_sum(violation_type_counts)
    cc = sum(compliance_type_counts.get(sev, 0) for sev in compliance_type_counts)
    if cc == 0 or wv == 0:
        return 0.0
    raw_lift = cc / (cc + wv)
    return raw_lift ** _LIFT_COMPRESS


def violation_ceiling(violation_type_counts: dict[str, int]) -> float:
    """Compute the maximum achievable score given the violation weight.

    ``ceiling = 10 - log2(1 + wv) * CEIL_SCALE``
    """
    wv = _weighted_sum(violation_type_counts)
    if wv == 0:
        return 10.0
    return 10.0 - math.log2(1.0 + wv) * _CEIL_SCALE


def severity_grade_floor(violation_type_counts: dict[str, int]) -> float:
    """Return the minimum score based on the worst violation severity present."""
    if violation_type_counts.get("critical", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["critical"]
    if violation_type_counts.get("major", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["major"]
    if violation_type_counts.get("minor", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["minor"]
    return 10.0


# ---------------------------------------------------------------------------
# Grade and legacy helpers
# ---------------------------------------------------------------------------

def score_to_grade_label(score: float) -> str:
    """Convert a 0-10 numerical score to a descriptive grade label."""
    for threshold, label in _GRADE_THRESHOLDS:
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
