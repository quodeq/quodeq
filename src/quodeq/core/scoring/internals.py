"""Internal constants and helper functions for the scoring engine."""
from __future__ import annotations

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

# Ratio-based dampening table: (min_compliance_to_violation_ratio, multiplier).
# Checked top-to-bottom; first matching row wins.
# Asymmetric: max discount 15%, max penalty 30%.
# Severity weights for dampening ratio: critical compliance/violations count
# more than minor ones, preventing cheap minor-compliance from offsetting
# critical violations.  Findings without a severity field default to minor (1).
_SEVERITY_WEIGHT = {"critical": 4, "major": 2, "minor": 1}
_MAX_PENALTY_MULTIPLIER = 1.30

_RATIO_DAMPENING_TABLE: list[tuple[float, float]] = [
    (3.0, 0.85),   # strong compliance evidence
    (2.0, 0.90),   # good compliance
    (1.0, 0.95),   # balanced
    (0.5, 1.00),   # neutral
    (0.0, 1.15),   # weak compliance (ratio > 0 but < 0.5)
    (-1.0, _MAX_PENALTY_MULTIPLIER),  # no compliance at all (sentinel, always matches)
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
    """Sum type counts weighted by severity (critical=4, major=2, minor=1)."""
    return sum(
        count * _SEVERITY_WEIGHT.get(sev, 1)
        for sev, count in type_counts.items()
    )


def compliance_dampening(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Compute the dampening multiplier from the compliance-to-violation ratio.

    Uses severity-weighted type counts so critical compliance has more
    impact than minor compliance, and minor compliance can't cheaply
    offset critical violations.

    Asymmetric: max discount 15% (0.85x), max penalty 30% (1.30x).
    No compliance at all gets the full 1.30x penalty.
    """
    weighted_compliance = _weighted_sum(compliance_type_counts)
    weighted_violations = _weighted_sum(violation_type_counts)

    if weighted_violations == 0:
        return 1.0  # no violations -> dampening is irrelevant

    if weighted_compliance == 0:
        return _MAX_PENALTY_MULTIPLIER  # no compliance at all -> max penalty

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


# ---------------------------------------------------------------------------
# Confidence interval
# ---------------------------------------------------------------------------

_CI_BASE_WIDTH = 1.0
_CI_LOW_CONFIDENCE_PENALTY = 1.0
_CI_MEDIUM_CONFIDENCE_PENALTY = 0.5
_CI_UNBALANCED_PENALTY = 0.5
_CI_SPARSITY_PENALTY = 0.5
_SPARSITY_RATIO = 0.01
_CI_UNSTABLE_THRESHOLD = 1.5
_GRADE_UNSTABLE_LABEL = "+/- 1 level"
_GRADE_STABLE_LABEL = "stable"


def confidence_interval_for(
    confidence_level: str,
    is_balanced: bool,
    total_instances: int,
    files_read: int = 0,
) -> dict:
    """Estimate the uncertainty width for a principle score.

    Starting width is 1.0. Additional half-points are added when:
    - confidence_level is 'low' (+1.0) or 'medium' (+0.5)
    - the sample is unbalanced (+0.5)
    - the instance count is sparse relative to files actually read (+0.5)

    grade_stability is 'stable' unless the interval exceeds 1.5.
    """
    width = _CI_BASE_WIDTH

    if confidence_level == "low":
        width += _CI_LOW_CONFIDENCE_PENALTY
    elif confidence_level == "medium":
        width += _CI_MEDIUM_CONFIDENCE_PENALTY

    if not is_balanced:
        width += _CI_UNBALANCED_PENALTY

    sparsity_floor = _SPARSITY_RATIO * files_read if files_read > 0 else 0
    if sparsity_floor > 0 and total_instances < sparsity_floor:
        width += _CI_SPARSITY_PENALTY

    return {
        "confidence_interval": width,
        "grade_stability": _GRADE_UNSTABLE_LABEL if width > _CI_UNSTABLE_THRESHOLD else _GRADE_STABLE_LABEL,
    }


# ---------------------------------------------------------------------------
# Numerical score -> grade label
# ---------------------------------------------------------------------------

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
