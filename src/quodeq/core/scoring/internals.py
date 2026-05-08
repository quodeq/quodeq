"""Scoring formula functions and re-exports for backward compatibility."""
from __future__ import annotations

import math

from quodeq.core.scoring._constants import (  # noqa: F401 — re-exports
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    _BASE_K,
    _CEIL_SCALE,
    _GRADE_THRESHOLDS,
    _LIFT_COMPRESS,
    _MAX_PENALTY_MULTIPLIER,
    _RATIO_DAMPENING_TABLE,
    _SCALE_TIERS,
    _SEVERITY_GRADE_FLOOR,
    _SEVERITY_WEIGHT,
    _WEIGHT_DOUBLE,
    _WEIGHT_TRIPLE,
    effective_cap_multiplier,
    scale_multiplier,
    small_project_multiplier,
)
from quodeq.core.scoring._tallies import (  # noqa: F401 — re-exports
    _tally_types,
    _weighted_sum,
    density_weighted_sum,
    evidence_has_taxonomy,
    tally_compliance_types_by_reason,
    tally_compliance_types_by_taxonomy,
    tally_types_by_reason,
    tally_types_by_taxonomy,
)
from quodeq.core.scoring.confidence import confidence_interval_for  # noqa: F401 — re-export
from quodeq.core.scoring.numerical import (  # noqa: F401 — re-export
    build_deductions,
    count_grade_drops,
)


# ---------------------------------------------------------------------------
# 4-stage scoring formula
# ---------------------------------------------------------------------------

def violation_base_from_wv(wv: float) -> float:
    """Hyperbolic base score from a precomputed weighted-violation total.

    Split out from :func:`violation_base` so principle-level scoring can
    feed in a density-aware weighted sum (see
    :func:`density_weighted_sum`) instead of the legacy distinct-type
    sum. Existing callers that only have ``vt_counts`` keep working
    through the wrapper below.
    """
    if wv == 0:
        return 10.0
    return 10.0 / (1.0 + _BASE_K * wv)


def violation_base(violation_type_counts: dict[str, int]) -> float:
    """Compute the base score from violations alone (ignoring compliance).

    Uses a hyperbolic curve: ``base = 10 / (1 + K * weighted_violations)``
    Returns a value in [0, 10].
    """
    return violation_base_from_wv(_weighted_sum(violation_type_counts))


def compliance_lift_from_wv(wc: float, wv: float) -> float:
    """Lift factor from precomputed weighted compliance/violation totals."""
    if wc == 0 or wv == 0:
        return 0.0
    raw_lift = wc / (wc + wv)
    return raw_lift ** _LIFT_COMPRESS


def compliance_lift(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Compute the lift factor from compliance evidence.

    Returns a value in [0, 1] representing the fraction of the gap filled.
    """
    wv = _weighted_sum(violation_type_counts)
    cc = sum(compliance_type_counts.get(sev, 0) for sev in compliance_type_counts)
    return compliance_lift_from_wv(cc, wv)


def violation_ceiling_from_wv(wv: float) -> float:
    """Ceiling score from a precomputed weighted-violation total."""
    if wv == 0:
        return 10.0
    return 10.0 - math.log2(1.0 + wv) * _CEIL_SCALE


def violation_ceiling(violation_type_counts: dict[str, int]) -> float:
    """Compute the maximum achievable score given the violation weight.

    ``ceiling = 10 - log2(1 + wv) * CEIL_SCALE``
    """
    return violation_ceiling_from_wv(_weighted_sum(violation_type_counts))


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
