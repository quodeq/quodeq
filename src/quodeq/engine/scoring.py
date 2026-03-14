from __future__ import annotations

from dataclasses import dataclass

from quodeq.engine.evidence import DEFAULT_WEIGHT, Evidence
from quodeq.engine.scoring_internals import (
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    scale_multiplier,
    build_deductions,
    compliance_dampening,
    confidence_interval_for,
    count_grade_drops,
    drop_grade,
    evidence_has_taxonomy,
    score_to_grade_label,
    tally_compliance_types_by_reason,
    tally_compliance_types_by_taxonomy,
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
    "grade_for_score",
    "run_scoring",
    "score_evidence",
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

@dataclass(frozen=True)
class _PrincipleContext:
    """Scoring context for a single principle — reduces parameter count."""
    key: str
    pdata: dict
    pct: float
    vt_counts: dict[str, int]
    dampening: float
    using_taxonomy: bool
    conf_level: str
    ci: dict
    scale_mult: int


def _score_principle_numerical(ctx: _PrincipleContext) -> dict:
    """Score a single principle in numerical mode."""
    if ctx.conf_level == "low":
        return {
            "display_name": ctx.pdata.get("display_name", ctx.key),
            "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
            "compliance_percentage": ctx.pct,
            "base_score": 0,
            "deductions": build_deductions({}, scale_multiplier=ctx.scale_mult),
            "final_score": 0.0,
            "grade": "Insufficient",
            "taxonomy_used": ctx.using_taxonomy,
            "confidence_level": ctx.conf_level,
            "confidence_interval": ctx.ci["confidence_interval"],
            "grade_stability": ctx.ci["grade_stability"],
        }

    base_pts = 10
    deductions = build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult)

    dampened_deduction = round(deductions["total_deduction"] * ctx.dampening, 2)
    effective_cap = min(deductions["critical_cap"], deductions["major_cap"])
    adjusted = min(effective_cap, round(base_pts - dampened_deduction, 1))
    final_pts = max(0.0, min(10.0, adjusted))

    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "base_score": base_pts,
        "deductions": deductions,
        "dampening_multiplier": ctx.dampening,
        "final_score": final_pts,
        "grade": score_to_grade_label(final_pts),
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }


def _score_principle_graded(ctx: _PrincipleContext) -> dict:
    """Score a single principle in non-numerical (graded) mode."""
    if ctx.conf_level == "low":
        return {
            "display_name": ctx.pdata.get("display_name", ctx.key),
            "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
            "compliance_percentage": ctx.pct,
            "base_grade": "Insufficient",
            "severity_drops": 0,
            "grade": "Insufficient",
            "taxonomy_used": ctx.using_taxonomy,
            "confidence_level": ctx.conf_level,
            "confidence_interval": ctx.ci["confidence_interval"],
            "grade_stability": ctx.ci["grade_stability"],
        }

    base_label = "Exemplary"
    level_drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    # Dampening can reduce drops: multiply then round down so partial drops
    # don't push the grade lower than the compliance evidence warrants.
    dampened_drops = int(level_drops * ctx.dampening)
    final_label = drop_grade(base_label, dampened_drops)

    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "base_grade": base_label,
        "severity_drops": level_drops,
        "dampening_multiplier": ctx.dampening,
        "grade": final_label,
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }


# ---------------------------------------------------------------------------
# Main scoring entry points
# ---------------------------------------------------------------------------

def _score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
) -> dict:
    """Score every principle in *raw_principles* and return the per-principle dict."""
    per_principle: dict = {}
    for key, pdata in raw_principles.items():
        metrics = pdata.get("metrics", {})
        pct = metrics.get("compliance_percentage", 0.0)
        violations = pdata.get("violations", [])
        compliance = pdata.get("compliance", [])
        conf_level = metrics.get("confidence_level", "medium")

        using_taxonomy = evidence_has_taxonomy(violations)
        vt_counts = (
            tally_types_by_taxonomy(violations)
            if using_taxonomy
            else tally_types_by_reason(violations)
        )
        ct_counts = (
            tally_compliance_types_by_taxonomy(compliance)
            if using_taxonomy
            else tally_compliance_types_by_reason(compliance)
        )
        dampen = compliance_dampening(ct_counts, vt_counts)
        ci = confidence_interval_for(
            confidence_level=conf_level,
            is_balanced=metrics.get("is_balanced", True),
            total_instances=metrics.get("total_instances", 0),
            files_read=files_read,
        )
        ctx = _PrincipleContext(
            key=key, pdata=pdata, pct=pct, vt_counts=vt_counts,
            dampening=dampen, using_taxonomy=using_taxonomy,
            conf_level=conf_level, ci=ci, scale_mult=scale_mult,
        )
        if mode == "numerical":
            per_principle[key] = _score_principle_numerical(ctx)
        else:
            per_principle[key] = _score_principle_graded(ctx)
    return per_principle


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
    source_file_count = evidence.get("source_file_count", 0)
    files_read = evidence.get("files_read", 0)
    scale_mult = scale_multiplier(source_file_count)

    per_principle = _score_all_principles(
        evidence.get("principles", {}), mode, scale_mult, files_read,
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


def _accumulate_weights(
    principles_scores: dict, mode: str,
) -> tuple[int, float, int, int]:
    """Sum weighted values across scorable principles.

    Returns (total_weight, total_value, total_count, insufficient_count).
    """
    total_count = len(principles_scores)
    insufficient_count = sum(
        1 for p in principles_scores.values() if p.get("grade") == "Insufficient"
    )
    total_weight = 0
    total_value = 0.0
    for pdata in principles_scores.values():
        if pdata.get("grade") == "Insufficient":
            continue
        multiplier = weight_as_multiplier(pdata.get("weight", DEFAULT_WEIGHT))
        total_weight += multiplier
        if mode == "numerical":
            total_value += pdata["final_score"] * multiplier
        else:
            total_value += GRADE_LADDER.index(pdata["grade"]) * multiplier
    return total_weight, total_value, total_count, insufficient_count


def _build_overall_result(mode: str, total_weight: int, total_value: float) -> dict:
    """Build the overall result dict from aggregated weights."""
    if mode == "numerical":
        mean_score = round(total_value / total_weight, 1)
        return {
            "weighted_score": mean_score,
            "grade": score_to_grade_label(mean_score),
            "total_weight": total_weight,
        }
    mean_index = total_value / total_weight
    ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
    return {"weighted_grade": GRADE_LADDER[ladder_pos], "total_weight": total_weight}


def _weighted_overall(principles_scores: dict, mode: str) -> dict:
    """Compute a weighted overall score or grade from per-principle results."""
    tw, tv, total, insuff = _accumulate_weights(principles_scores, mode)

    if tw == 0:
        if mode == "numerical":
            return {"weighted_score": 0.0, "grade": "Insufficient"}
        return {"weighted_grade": "Insufficient"}

    result = _build_overall_result(mode, tw, tv)

    if total > 0 and insuff > total / 2:
        scored = total - insuff
        result["confidence"] = "low"
        result["confidence_reason"] = (
            f"Only {scored}/{total} principles had sufficient evidence"
        )
    return result


def score_evidence(evidence: Evidence, mode: str = "numerical") -> dict:
    """Score Evidence using the scoring engine."""
    ev_dict = evidence.to_evidence_dict()
    return run_scoring(ev_dict, mapping={}, mode=mode)
