from __future__ import annotations

from codecompass.evaluate.lib.evidence import DEFAULT_WEIGHT

# ---------------------------------------------------------------------------
# Lookup tables
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
_GRADE_LADDER: list[str] = [
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
_MAJOR_PENALTY = 0.25     # per distinct major violation type, cap 5 types


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

def build_deductions(violation_type_counts: dict[str, int]) -> dict:
    """Compute point deductions for numerical mode.

    Rules:
    - Each distinct critical violation type removes 1.0 point (cap: 3 types max)
    - Each distinct major violation type removes 0.25 points (cap: 5 types max)
    - If criticals are present the score is capped at 3; if majors are present
      the score is capped at 5; both caps may apply simultaneously (take min).
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)

    critical_deduction = n_critical * _CRITICAL_PENALTY
    major_deduction = n_major * _MAJOR_PENALTY

    cap_from_critical = 3 if n_critical > 0 else 10
    cap_from_major = 5 if n_major > 0 else 10

    return {
        "critical_type_count": n_critical,
        "major_type_count": n_major,
        "critical_deduction": critical_deduction,
        "major_deduction": major_deduction,
        "total_deduction": critical_deduction + major_deduction,
        "critical_cap": cap_from_critical,
        "major_cap": cap_from_major,
    }


def count_grade_drops(violation_type_counts: dict[str, int]) -> int:
    """Return the number of grade levels to drop in non-numerical mode.

    Critical and major types are evaluated independently against their
    progressive threshold tables; the larger of the two drop values wins.
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)

    critical_drops = 0
    for min_count, levels in _CRITICAL_DROP_TABLE:
        if n_critical >= min_count:
            critical_drops = levels
            break

    major_drops = 0
    for min_count, levels in _MAJOR_DROP_TABLE:
        if n_major >= min_count:
            major_drops = levels
            break

    return max(critical_drops, major_drops)


def drop_grade(grade: str, drops: int) -> str:
    """Reduce a grade by the requested number of levels, flooring at Insufficient."""
    position = _GRADE_LADDER.index(grade)
    new_position = max(0, position - drops)
    return _GRADE_LADDER[new_position]


# ---------------------------------------------------------------------------
# Confidence interval
# ---------------------------------------------------------------------------

def confidence_interval_for(
    confidence_level,
    is_balanced: bool,
    total_instances: int,
    source_file_count: int,
) -> dict:
    """Estimate the uncertainty width for a principle score.

    Starting width is 1.0. Additional half-points are added when:
    - confidence_level is 'low' (+1.0) or 'medium' (+0.5)
    - the sample is unbalanced (+0.5)
    - the instance count is sparse relative to source file count (+0.5)

    grade_stability is 'stable' unless the interval exceeds 1.5.
    """
    width = 1.0

    if confidence_level == "low":
        width += 1.0
    elif confidence_level == "medium":
        width += 0.5

    if not is_balanced:
        width += 0.5

    sparsity_floor = 0.01 * source_file_count if source_file_count > 0 else 0
    if total_instances < sparsity_floor:
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


# ---------------------------------------------------------------------------
# Main scoring entry points
# ---------------------------------------------------------------------------

def run_scoring(evidence: dict, mapping: dict, mode: str) -> dict:
    """Compute per-principle scores and return the full result dictionary.

    Args:
        evidence: Parsed evidence JSON for a single evaluation dimension.
        mapping:  Parsed mapping JSON (not used internally but kept for API
                  compatibility with callers that pass it).
        mode:     'numerical' or 'non-numerical'.

    Returns:
        A dict with keys: repository, discipline, date, mode, principles, overall.
    """
    per_principle: dict = {}
    raw_principles = evidence.get("principles", {})

    for key, pdata in raw_principles.items():
        metrics = pdata.get("metrics", {})
        pct = metrics.get("compliance_percentage", 0.0)
        violations = pdata.get("violations", [])
        weight_label = pdata.get("weight", DEFAULT_WEIGHT)
        conf_level = metrics.get("confidence_level", "medium")

        using_taxonomy = evidence_has_taxonomy(violations)
        vt_counts = (
            tally_types_by_taxonomy(violations)
            if using_taxonomy
            else tally_types_by_reason(violations)
        )

        ci = confidence_interval_for(
            confidence_level=conf_level,
            is_balanced=metrics.get("is_balanced", True),
            total_instances=metrics.get("total_instances", 0),
            source_file_count=evidence.get("source_file_count", 0),
        )

        if mode == "numerical":
            base_pts = score_for_compliance(pct)
            deductions = build_deductions(vt_counts)

            effective_cap = min(deductions["critical_cap"], deductions["major_cap"])
            adjusted = min(effective_cap, round(base_pts - deductions["total_deduction"]))

            no_serious_violations = (
                deductions["critical_type_count"] == 0
                and deductions["major_type_count"] == 0
            )
            bonus = 1 if no_serious_violations else 0
            final_pts = min(10, adjusted + bonus)

            per_principle[key] = {
                "display_name": pdata.get("display_name", key),
                "weight": weight_label,
                "compliance_percentage": pct,
                "base_score": base_pts,
                "deductions": deductions,
                "minor_only_bonus": bonus,
                "final_score": final_pts,
                "grade": score_to_grade_label(final_pts),
                "taxonomy_used": using_taxonomy,
                "confidence_level": conf_level,
                "confidence_interval": ci["confidence_interval"],
                "grade_stability": ci["grade_stability"],
            }

        else:  # non-numerical
            base_label = grade_for_compliance(pct)
            level_drops = count_grade_drops(vt_counts)
            final_label = drop_grade(base_label, level_drops)

            per_principle[key] = {
                "display_name": pdata.get("display_name", key),
                "weight": weight_label,
                "compliance_percentage": pct,
                "base_grade": base_label,
                "severity_drops": level_drops,
                "grade": final_label,
                "taxonomy_used": using_taxonomy,
                "confidence_level": conf_level,
                "confidence_interval": ci["confidence_interval"],
                "grade_stability": ci["grade_stability"],
            }

    overall = _weighted_overall(per_principle, mode)

    return {
        "repository": evidence.get("repository", ""),
        "discipline": evidence.get("discipline", ""),
        "date": evidence.get("date", ""),
        "mode": mode,
        "principles": per_principle,
        "overall": overall,
    }


def _weighted_overall(principles_scores: dict, mode: str) -> dict:
    """Compute a weighted overall score or grade from per-principle results.

    Each principle's weight string is parsed to an integer multiplier. In
    numerical mode the weighted mean of final_score values is returned. In
    non-numerical mode grades are converted to ladder indices, the weighted
    mean is computed, and the result is rounded back to the nearest grade.
    """
    total_weight = 0
    total_value = 0.0

    for pdata in principles_scores.values():
        multiplier = weight_as_multiplier(pdata.get("weight", DEFAULT_WEIGHT))
        total_weight += multiplier

        if mode == "numerical":
            total_value += pdata["final_score"] * multiplier
        else:
            grade_index = _GRADE_LADDER.index(pdata["grade"])
            total_value += grade_index * multiplier

    if total_weight == 0:
        if mode == "numerical":
            return {"weighted_score": 0.0, "grade": "Critical"}
        return {"weighted_grade": "Insufficient"}

    if mode == "numerical":
        mean_score = round(total_value / total_weight, 1)
        return {
            "weighted_score": mean_score,
            "grade": score_to_grade_label(mean_score),
            "total_weight": total_weight,
        }
    else:
        mean_index = total_value / total_weight
        ladder_pos = min(len(_GRADE_LADDER) - 1, round(mean_index))
        return {
            "weighted_grade": _GRADE_LADDER[ladder_pos],
            "total_weight": total_weight,
        }
