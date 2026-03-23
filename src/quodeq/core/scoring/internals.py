"""Internal constants and helper functions for the scoring engine."""
from __future__ import annotations

import math

from quodeq.core.scoring.confidence import confidence_interval_for  # noqa: F401 — re-export
from quodeq.core.scoring.numerical import (  # noqa: F401 — re-export
    build_deductions,
    count_grade_drops,
)

# ---------------------------------------------------------------------------
# Constants and lookup tables
# ---------------------------------------------------------------------------

# Canonical ordering from worst to best — used to convert grades to integers
# for arithmetic and to clamp drop operations.
GRADE_LADDER: list[str] = [
    "Insufficient",
    "Developing",
    "Proficient",
    "Exemplary",
]

# ---------------------------------------------------------------------------
# Violation severity weights (for weighted violation count)
# ---------------------------------------------------------------------------
_SEVERITY_WEIGHT = {"critical": 4.0, "major": 1.5, "minor": 0.25}

# Base score curve: base = 10 / (1 + K * weighted_violations)
# K controls how fast violations pull the score down.
# K=0.12: 3 critical (wv=12) → base 4.1, 5 major (wv=7.5) → base 5.3
_BASE_K = 0.12

# Compliance lift curve: lift = (compliance_count / (compliance_count + wv))^COMPRESS
# Higher COMPRESS → harder to reach Exemplary via compliance alone.
_LIFT_COMPRESS = 1.8

# Violation ceiling: ceiling = 10 - log2(1 + wv) * CEIL_SCALE
# Uses weighted violations so minor violations barely affect the ceiling
# while major/critical violations bring it down properly.
_CEIL_SCALE = 0.5

# Severity grade floor: grade cannot be worse than the severities present.
# Only-minor violations → floor at Adequate (5.0)
# Has-major (no critical) → floor at Poor (3.0)
# Has-critical → no floor (score can reach Critical grade)
_SEVERITY_GRADE_FLOOR: dict[str, float] = {
    "critical": 0.0,
    "major": 3.0,
    "minor": 5.0,
}

# Legacy: kept for non-numerical (graded) mode compatibility
_MAX_PENALTY_MULTIPLIER = 1.30
_RATIO_DAMPENING_TABLE: list[tuple[float, float]] = [
    (3.0, 0.85),
    (2.0, 0.90),
    (1.0, 0.95),
    (0.5, 1.00),
    (0.0, 1.15),
    (-1.0, _MAX_PENALTY_MULTIPLIER),
]

# ---------------------------------------------------------------------------
# Project-size scaling
# ---------------------------------------------------------------------------
# Scoring algorithm constants — modify via plugin configuration, not env vars.
# Each entry is (min_file_count_inclusive, multiplier).
# Tiers: Small (<500) x1 | Medium (500-5k) x2 | Large (5k-20k) x3
#        XLarge (20k-50k) x4 | XXLarge (50k-100k) x5 | Enterprise (100k+) x6
_SCALE_TIERS: list[tuple[int, int]] = [
    (100_000, 6),
    ( 50_000, 5),
    ( 20_000, 4),
    (  5_000, 3),
    (    500, 2),
    (      0, 1),
]

SCALE_TIER_NAMES: dict[int, str] = {
    1: "Small",
    2: "Medium",
    3: "Large",
    4: "XLarge",
    5: "XXLarge",
    6: "Enterprise",
}


def scale_multiplier(source_file_count: int) -> int:
    """Return the size-based scaling multiplier for a project."""
    for threshold, multiplier in _SCALE_TIERS:
        if source_file_count >= threshold:
            return multiplier
    return 1


# ---------------------------------------------------------------------------
# Violation-type counting
# ---------------------------------------------------------------------------

def _tally_types(items: list[dict], key_field: str, skip_empty: bool = False) -> dict[str, int]:
    """Count distinct types per severity bucket.

    *key_field* selects which dict key to group by (e.g. ``"vt"`` or ``"reason"``).
    When *skip_empty* is ``True``, items whose *key_field* is falsy are ignored.
    """
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in items:
        value = item.get(key_field)
        if skip_empty and not value:
            continue
        if value is None:
            value = "unknown"
        sev = item.get("severity", "minor")
        buckets.setdefault(sev, set()).add(value)
    return {sev: len(seen) for sev, seen in buckets.items()}


def tally_types_by_taxonomy(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using the 'vt' taxonomy field.

    Only violations that carry a non-empty 'vt' value contribute; each unique
    (severity, vt) combination is counted once.
    """
    return _tally_types(violations, "vt", skip_empty=True)


def tally_types_by_reason(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using (severity, reason) pairs.

    Used when no 'vt' field is present in the evidence; each unique reason
    string within a severity bucket is treated as one violation type.
    """
    return _tally_types(violations, "reason")


def evidence_has_taxonomy(violations: list[dict]) -> bool:
    """Return True if at least one violation carries a 'vt' field."""
    return any(item.get("vt") for item in violations)


# ---------------------------------------------------------------------------
# Compliance counting & dampening
# ---------------------------------------------------------------------------

def tally_compliance_types_by_taxonomy(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using the 'vt' field."""
    return _tally_types(compliance, "vt", skip_empty=True)


def tally_compliance_types_by_reason(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using (severity, reason) pairs."""
    return _tally_types(compliance, "reason")


def _weighted_sum(type_counts: dict[str, int]) -> float:
    """Sum type counts weighted by severity."""
    return sum(
        count * _SEVERITY_WEIGHT.get(sev, 0.25)
        for sev, count in type_counts.items()
    )


def violation_base(violation_type_counts: dict[str, int]) -> float:
    """Compute the base score from violations alone (ignoring compliance).

    Uses a hyperbolic curve with diminishing returns:
    ``base = 10 / (1 + K * weighted_violations)``

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

    Compliance fills the gap between the violation base and 10.
    Uses uniform compliance count (each item = 1) with a compressed
    power curve so reaching the top requires a strong ratio.

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

    Uses a log2 curve on weighted violations so minor violations barely
    affect the ceiling while major/critical bring it down.

    ``ceiling = 10 - log2(1 + wv) * CEIL_SCALE``
    """
    wv = _weighted_sum(violation_type_counts)
    if wv == 0:
        return 10.0
    return 10.0 - math.log2(1.0 + wv) * _CEIL_SCALE


def severity_grade_floor(violation_type_counts: dict[str, int]) -> float:
    """Return the minimum score based on the worst violation severity present.

    - Only minor violations -> floor at 5.0 (Adequate)
    - Has major (no critical) -> floor at 3.0 (Poor)
    - Has critical -> floor at 0.0 (no protection)
    - No violations -> floor at 10.0
    """
    if violation_type_counts.get("critical", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["critical"]
    if violation_type_counts.get("major", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["major"]
    if violation_type_counts.get("minor", 0) > 0:
        return _SEVERITY_GRADE_FLOOR["minor"]
    return 10.0


def compliance_dampening(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Legacy dampening multiplier — used by the non-numerical (graded) mode.

    Uses severity-weighted type counts to compute a compliance-to-violation
    ratio, then maps it to a multiplier via the dampening table.
    """
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


_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (9, "Exemplary"),
    (7, "Good"),
    (5, "Adequate"),
    (3, "Poor"),
]


def score_to_grade_label(score: float) -> str:
    """Convert a 0-10 numerical score to a descriptive grade label."""
    for threshold, label in _GRADE_THRESHOLDS:
        if score >= threshold:
            return label
    return "Critical"


# ---------------------------------------------------------------------------
# Weight parsing
# ---------------------------------------------------------------------------

_WEIGHT_TRIPLE = "x3"
_WEIGHT_DOUBLE = "x2"


def weight_as_multiplier(weight_str: str) -> int:
    """Extract the integer multiplier from a weight label like 'High (x3)'.

    Recognises 'x3' -> 3, 'x2' -> 2, anything else -> 1.
    """
    if _WEIGHT_TRIPLE in weight_str:
        return 3
    if _WEIGHT_DOUBLE in weight_str:
        return 2
    return 1
