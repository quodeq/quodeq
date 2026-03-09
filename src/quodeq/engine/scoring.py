from __future__ import annotations

from quodeq.engine.evidence import DEFAULT_WEIGHT, Evidence
from quodeq.engine.scoring_internals import (
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    _scale_multiplier,
    build_deductions,
    confidence_interval_for,
    count_grade_drops,
    drop_grade,
    evidence_has_taxonomy,
    grade_for_compliance,
    score_for_compliance,
    score_to_grade_label,
    tally_types_by_reason,
    tally_types_by_taxonomy,
    weight_as_multiplier,
)

# Re-export public API symbols that other modules may import from here.
__all__ = [
    "DEFAULT_WEIGHT",
    "build_deductions",
    "confidence_interval_for",
    "confidence_label",
    "count_grade_drops",
    "drop_grade",
    "evidence_has_taxonomy",
    "grade_for_compliance",
    "grade_for_score",
    "run_scoring",
    "score_evidence",
    "score_for_compliance",
    "score_to_grade_label",
    "tally_types_by_reason",
    "tally_types_by_taxonomy",
    "weight_as_multiplier",
]


def grade_for_score(score: float) -> str:
    """Alias for score_to_grade_label — kept for public API compatibility."""
    return score_to_grade_label(score)


def confidence_label(level: str) -> str:
    """Return a human-readable confidence label."""
    return {"low": "Low", "medium": "Medium", "high": "High"}.get(level, level)


# ---------------------------------------------------------------------------
# Branch helpers for run_scoring
# ---------------------------------------------------------------------------

def _score_principle_numerical(
    key: str,
    pdata: dict,
    pct: float,
    vt_counts: dict[str, int],
    using_taxonomy: bool,
    conf_level: str,
    ci: dict,
    scale_mult: int,
) -> dict:
    """Score a single principle in numerical mode."""
    base_pts = score_for_compliance(pct)
    deductions = build_deductions(vt_counts, scale_multiplier=scale_mult)

    effective_cap = min(deductions["critical_cap"], deductions["major_cap"])
    adjusted = min(effective_cap, round(base_pts - deductions["total_deduction"], 1))
    final_pts = max(0.0, min(10.0, adjusted))

    return {
        "display_name": pdata.get("display_name", key),
        "weight": pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": pct,
        "base_score": base_pts,
        "deductions": deductions,
        "final_score": final_pts,
        "grade": score_to_grade_label(final_pts),
        "taxonomy_used": using_taxonomy,
        "confidence_level": conf_level,
        "confidence_interval": ci["confidence_interval"],
        "grade_stability": ci["grade_stability"],
    }


def _score_principle_graded(
    key: str,
    pdata: dict,
    pct: float,
    vt_counts: dict[str, int],
    using_taxonomy: bool,
    conf_level: str,
    ci: dict,
    scale_mult: int,
) -> dict:
    """Score a single principle in non-numerical (graded) mode."""
    base_label = grade_for_compliance(pct)
    level_drops = count_grade_drops(vt_counts, scale_multiplier=scale_mult)
    final_label = drop_grade(base_label, level_drops)

    return {
        "display_name": pdata.get("display_name", key),
        "weight": pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": pct,
        "base_grade": base_label,
        "severity_drops": level_drops,
        "grade": final_label,
        "taxonomy_used": using_taxonomy,
        "confidence_level": conf_level,
        "confidence_interval": ci["confidence_interval"],
        "grade_stability": ci["grade_stability"],
    }


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
    source_file_count = evidence.get("source_file_count", 0)
    files_read = evidence.get("files_read", 0)
    scale_mult = _scale_multiplier(source_file_count)
    raw_principles = evidence.get("principles", {})

    for key, pdata in raw_principles.items():
        metrics = pdata.get("metrics", {})
        pct = metrics.get("compliance_percentage", 0.0)
        violations = pdata.get("violations", [])
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
            files_read=files_read,
        )

        if mode == "numerical":
            per_principle[key] = _score_principle_numerical(
                key, pdata, pct, vt_counts, using_taxonomy, conf_level, ci, scale_mult,
            )
        else:
            per_principle[key] = _score_principle_graded(
                key, pdata, pct, vt_counts, using_taxonomy, conf_level, ci, scale_mult,
            )

    overall = _weighted_overall(per_principle, mode)

    return {
        "repository": evidence.get("repository", ""),
        "discipline": evidence.get("discipline", ""),
        "date": evidence.get("date", ""),
        "mode": mode,
        "principles": per_principle,
        "overall": overall,
        "scale": {
            "tier": SCALE_TIER_NAMES.get(scale_mult, "Small"),
            "multiplier": scale_mult,
            "files_read": files_read,
        },
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
            grade_index = GRADE_LADDER.index(pdata["grade"])
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
        ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
        return {
            "weighted_grade": GRADE_LADDER[ladder_pos],
            "total_weight": total_weight,
        }


def score_evidence(evidence: Evidence, mode: str = "numerical") -> dict:
    """Score Evidence using the scoring engine."""
    ev_dict = evidence.to_evidence_dict()
    return run_scoring(ev_dict, mapping={}, mode=mode)
