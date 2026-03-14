"""Internal constants and helper functions for the scoring engine."""
from __future__ import annotations

from quodeq.engine._scoring_numerical import (  # noqa: F401 — re-export
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
# Uses raw distinct type counts (no severity weighting) to avoid bias from
# compliance findings that lack proper severity fields.
_RATIO_DAMPENING_TABLE: list[tuple[float, float]] = [
    (3.0, 0.85),   # strong compliance evidence
    (2.0, 0.90),   # good compliance
    (1.0, 0.95),   # balanced
    (0.5, 1.00),   # neutral
    (0.0, 1.15),   # weak compliance (ratio > 0 but < 0.5)
    (-1.0, 1.30),  # no compliance at all (sentinel, always matches)
]

# ---------------------------------------------------------------------------
# Project-size scaling
# ---------------------------------------------------------------------------
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

def tally_types_by_taxonomy(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using the 'vt' taxonomy field.

    Only violations that carry a non-empty 'vt' value contribute; each unique
    (severity, vt) combination is counted once.
    """
    buckets: dict[str, set] = {
        "critical": set(),
        "major": set(),
        "minor": set(),
    }
    for item in violations:
        vt_tag = item.get("vt")
        if not vt_tag:
            continue
        sev = item.get("severity", "minor")
        buckets.setdefault(sev, set()).add(vt_tag)
    return {sev: len(seen) for sev, seen in buckets.items()}


def tally_types_by_reason(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using (severity, reason) pairs.

    Used when no 'vt' field is present in the evidence; each unique reason
    string within a severity bucket is treated as one violation type.
    """
    buckets: dict[str, set] = {
        "critical": set(),
        "major": set(),
        "minor": set(),
    }
    for item in violations:
        sev = item.get("severity", "minor")
        reason = item.get("reason", "unknown")
        buckets.setdefault(sev, set()).add(reason)
    return {sev: len(seen) for sev, seen in buckets.items()}


def evidence_has_taxonomy(violations: list[dict]) -> bool:
    """Return True if at least one violation carries a 'vt' field."""
    return any(item.get("vt") for item in violations)


# ---------------------------------------------------------------------------
# Compliance counting & dampening
# ---------------------------------------------------------------------------

def tally_compliance_types_by_taxonomy(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using the 'vt' field."""
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in compliance:
        vt_tag = item.get("vt")
        if not vt_tag:
            continue
        sev = item.get("severity", "minor")
        buckets.setdefault(sev, set()).add(vt_tag)
    return {sev: len(seen) for sev, seen in buckets.items()}


def tally_compliance_types_by_reason(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using (severity, reason) pairs."""
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in compliance:
        sev = item.get("severity", "minor")
        reason = item.get("reason", "unknown")
        buckets.setdefault(sev, set()).add(reason)
    return {sev: len(seen) for sev, seen in buckets.items()}


def compliance_dampening(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
) -> float:
    """Compute the dampening multiplier from the compliance-to-violation ratio.

    Uses raw distinct type counts (sum across all severities, no weighting)
    to avoid bias from compliance findings that lack severity fields.

    Asymmetric: max discount 15% (0.85×), max penalty 30% (1.30×).
    No compliance at all gets the full 1.30× penalty.
    """
    total_compliance = sum(compliance_type_counts.values())
    total_violations = sum(violation_type_counts.values())

    if total_violations == 0:
        return 1.0  # no violations → dampening is irrelevant

    if total_compliance == 0:
        return 1.30  # no compliance at all → max penalty

    ratio = total_compliance / total_violations
    for threshold, multiplier in _RATIO_DAMPENING_TABLE:
        if ratio >= threshold:
            return multiplier
    return 1.30


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
    width = 1.0

    if confidence_level == "low":
        width += 1.0
    elif confidence_level == "medium":
        width += 0.5

    if not is_balanced:
        width += 0.5

    sparsity_floor = 0.01 * files_read if files_read > 0 else 0
    if sparsity_floor > 0 and total_instances < sparsity_floor:
        width += 0.5

    return {
        "confidence_interval": width,
        "grade_stability": "± 1 level" if width > 1.5 else "stable",
    }


# ---------------------------------------------------------------------------
# Numerical score → grade label
# ---------------------------------------------------------------------------

def score_to_grade_label(score: float) -> str:
    """Convert a 0–10 numerical score to a descriptive grade label."""
    if score >= 9:
        return "Exemplary"
    if score >= 7:
        return "Good"
    if score >= 5:
        return "Adequate"
    if score >= 3:
        return "Poor"
    return "Critical"


# ---------------------------------------------------------------------------
# Weight parsing
# ---------------------------------------------------------------------------

def weight_as_multiplier(weight_str: str) -> int:
    """Extract the integer multiplier from a weight label like 'High (x3)'.

    Recognises 'x3' → 3, 'x2' → 2, anything else → 1.
    """
    if "x3" in weight_str:
        return 3
    if "x2" in weight_str:
        return 2
    return 1
