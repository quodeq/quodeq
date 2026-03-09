"""Internal constants and helper functions for the scoring engine."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants and lookup tables
# ---------------------------------------------------------------------------

# Each entry is (minimum_compliance_pct_exclusive, score).
# Walk the list top-to-bottom; the first threshold the compliance % exceeds
# wins. Last row acts as a catch-all for the 0 % case.
_SCORE_BANDS: list[tuple[float, int]] = [
    (70.0, 10),
    (55.0, 9),
    (45.0, 8),
    (38.0, 7),
    (30.0, 6),
    (25.0, 5),
    (18.0, 4),
    (12.0, 3),
    (5.0, 2),
    (1.0, 1),
    (0.0, 0),
]

# Same idea for non-numerical grades. Compliance must be *strictly above*
# the threshold to earn that grade.
_GRADE_BANDS: list[tuple[float, str]] = [
    (72.0, "Exemplary"),
    (48.0, "Proficient"),
    (20.0, "Developing"),
]

# Canonical ordering from worst to best — used to convert grades to integers
# for arithmetic and to clamp drop operations.
GRADE_LADDER: list[str] = [
    "Insufficient",
    "Developing",
    "Proficient",
    "Exemplary",
]

# Progressive drop tables: (min_type_count_inclusive, levels_to_drop).
# Checked top-to-bottom; first matching row wins.
_CRITICAL_DROP_TABLE: list[tuple[int, int]] = [(12, 3), (4, 2), (1, 1)]
_MAJOR_DROP_TABLE: list[tuple[int, int]] = [(36, 3), (12, 2), (4, 1)]

# Per-type deduction constants for numerical mode.
_CRITICAL_PENALTY = 1.0   # per distinct critical violation type, cap 3 types
_MAJOR_PENALTY = 0.5      # per distinct major violation type, cap 5 types
_MINOR_PENALTY = 0.1      # per distinct minor violation type

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


def _scale_multiplier(source_file_count: int) -> int:
    """Return the size-based scaling multiplier for a project."""
    for threshold, multiplier in _SCALE_TIERS:
        if source_file_count >= threshold:
            return multiplier
    return 1


# ---------------------------------------------------------------------------
# Band lookups
# ---------------------------------------------------------------------------

def score_for_compliance(compliance_pct: float) -> int:
    """Map a compliance percentage to a 0–10 base score via threshold bands."""
    for min_pct, pts in _SCORE_BANDS:
        if compliance_pct > min_pct:
            return pts
    return 0


def grade_for_compliance(compliance_pct: float) -> str:
    """Map a compliance percentage to a grade word via threshold bands."""
    for min_pct, label in _GRADE_BANDS:
        if compliance_pct > min_pct:
            return label
    return "Insufficient"


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
# Deduction / drop computation
# ---------------------------------------------------------------------------

def build_deductions(violation_type_counts: dict[str, int], scale_multiplier: int = 1) -> dict:
    """Compute point deductions for numerical mode.

    Rules:
    - Each distinct critical violation type removes 1.0 point; types are capped
      at 3*scale before computing the deduction.
    - Each distinct major violation type removes 0.5 points; capped at 5*scale.
    - Each distinct minor violation type removes 0.1 points; capped at 2*scale.
    - If the raw critical count reaches 3*scale, the score is hard-capped at 3.
    - If the raw major count reaches 5*scale, the score is hard-capped at 5.
    - Both caps may apply simultaneously (take min).
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)
    n_minor = violation_type_counts.get("minor", 0)

    critical_type_cap = 3 * scale_multiplier
    major_type_cap = 5 * scale_multiplier
    minor_type_cap = 2 * scale_multiplier

    effective_critical = min(n_critical, critical_type_cap)
    effective_major = min(n_major, major_type_cap)
    effective_minor = min(n_minor, minor_type_cap)

    critical_deduction = effective_critical * _CRITICAL_PENALTY
    major_deduction = effective_major * _MAJOR_PENALTY
    minor_deduction = effective_minor * _MINOR_PENALTY

    cap_from_critical = 3 if n_critical >= critical_type_cap else 10
    cap_from_major = 5 if n_major >= major_type_cap else 10

    return {
        "critical_type_count": n_critical,
        "major_type_count": n_major,
        "minor_type_count": n_minor,
        "critical_deduction": critical_deduction,
        "major_deduction": major_deduction,
        "minor_deduction": minor_deduction,
        "total_deduction": critical_deduction + major_deduction + minor_deduction,
        "critical_cap": cap_from_critical,
        "major_cap": cap_from_major,
    }


def count_grade_drops(violation_type_counts: dict[str, int], scale_multiplier: int = 1) -> int:
    """Return the number of grade levels to drop in non-numerical mode.

    Drop table thresholds are multiplied by scale_multiplier so that large
    projects require proportionally more violation types before incurring drops.
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)

    critical_drops = 0
    for min_count, levels in _CRITICAL_DROP_TABLE:
        if n_critical >= min_count * scale_multiplier:
            critical_drops = levels
            break

    major_drops = 0
    for min_count, levels in _MAJOR_DROP_TABLE:
        if n_major >= min_count * scale_multiplier:
            major_drops = levels
            break

    return max(critical_drops, major_drops)


def drop_grade(grade: str, drops: int) -> str:
    """Reduce a grade by the requested number of levels, flooring at Insufficient."""
    position = GRADE_LADDER.index(grade)
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
