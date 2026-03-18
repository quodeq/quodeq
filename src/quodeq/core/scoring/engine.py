from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.types import Deductions, OverallScore, PrincipleScore, ScaleInfo, ScoringResult
from quodeq.core.evidence.model import DEFAULT_WEIGHT, Evidence
from quodeq.core.scoring.overall import (
    _accumulate_weights,
    _build_overall_result,
    _weighted_overall,
    MODE_NUMERICAL,
)
from quodeq.core.scoring.internals import (
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    scale_multiplier,
    build_deductions,
    compliance_dampening,
    compliance_lift,
    confidence_interval_for,
    count_grade_drops,
    drop_grade,
    evidence_has_taxonomy,
    score_to_grade_label,
    severity_grade_floor,
    tally_compliance_types_by_reason,
    tally_compliance_types_by_taxonomy,
    tally_types_by_reason,
    tally_types_by_taxonomy,
    violation_base,
    violation_ceiling,
    weight_as_multiplier,
)

# Re-export public API symbols that other modules may import from here.
_BASE_SCORE = 10

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
    ct_counts: dict[str, int]
    dampening: float
    using_taxonomy: bool
    conf_level: str
    ci: dict
    scale_mult: int


def _base_principle_kwargs(ctx: _PrincipleContext) -> dict:
    """Build the common keyword arguments shared by both scoring modes."""
    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }


def _score_principle_numerical(ctx: _PrincipleContext) -> PrincipleScore:
    """Score a single principle in numerical mode.

    Uses a three-constraint model:
    1. BASE:    Violation severity determines the starting score.
    2. LIFT:    Compliance evidence fills the gap toward 10.
    3. CEILING: Weighted violation count caps the maximum achievable score.
    4. FLOOR:   Grade cannot be worse than the violation severities justify.
    """
    kwargs = _base_principle_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs,
            base_score=0,
            deductions=build_deductions({}, scale_multiplier=ctx.scale_mult),
            final_score=0.0,
            grade="Insufficient",
        )

    # Stage 1: base from violation severity
    base = violation_base(ctx.vt_counts)

    # Stage 2: compliance lifts toward 10
    lift = compliance_lift(ctx.ct_counts, ctx.vt_counts)
    raw_score = base + (_BASE_SCORE - base) * lift

    # Stage 3: ceiling from weighted violation count
    ceiling = violation_ceiling(ctx.vt_counts)

    # Stage 4: severity grade floor
    floor = severity_grade_floor(ctx.vt_counts)

    final_pts = round(max(floor, min(ceiling, raw_score)), 1)

    # Build legacy Deductions for backward compat with report serialization
    deductions = build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult)

    return PrincipleScore(
        **kwargs,
        base_score=round(base, 1),
        deductions=deductions,
        dampening_multiplier=lift,
        final_score=final_pts,
        grade=score_to_grade_label(final_pts),
    )


def _score_principle_graded(ctx: _PrincipleContext) -> PrincipleScore:
    """Score a single principle in non-numerical (graded) mode."""
    kwargs = _base_principle_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs,
            base_grade="Insufficient",
            severity_drops=0,
            grade="Insufficient",
        )

    base_label = "Exemplary"
    level_drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    # Dampening can reduce drops: multiply then round down so partial drops
    # don't push the grade lower than the compliance evidence warrants.
    dampened_drops = int(level_drops * ctx.dampening)
    final_label = drop_grade(base_label, dampened_drops)

    return PrincipleScore(
        **kwargs,
        base_grade=base_label,
        severity_drops=level_drops,
        dampening_multiplier=ctx.dampening,
        grade=final_label,
    )


# ---------------------------------------------------------------------------
# Main scoring entry points
# ---------------------------------------------------------------------------

def _build_principle_context(
    key: str, pdata: dict, scale_mult: int, files_read: int,
) -> _PrincipleContext:
    """Extract evidence data for a single principle and return a scoring context."""
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
    return _PrincipleContext(
        key=key, pdata=pdata, pct=pct, vt_counts=vt_counts,
        ct_counts=ct_counts, dampening=dampen, using_taxonomy=using_taxonomy,
        conf_level=conf_level, ci=ci, scale_mult=scale_mult,
    )


def _score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
) -> dict[str, PrincipleScore]:
    """Score every principle in *raw_principles* and return the per-principle dict."""
    scorer = _score_principle_numerical if mode == MODE_NUMERICAL else _score_principle_graded
    per_principle: dict[str, PrincipleScore] = {}
    for key, pdata in raw_principles.items():
        ctx = _build_principle_context(key, pdata, scale_mult, files_read)
        per_principle[key] = scorer(ctx)
    return per_principle


def run_scoring(evidence: dict, mode: str) -> ScoringResult:
    """Compute per-principle scores and return the full result.

    Args:
        evidence: Parsed evidence JSON for a single evaluation dimension.
        mode:     'numerical' or 'non-numerical'.

    Returns:
        A ScoringResult with principles, overall, and scale info.
    """
    source_file_count = evidence.get("source_file_count", 0)
    files_read = evidence.get("files_read", 0)
    scale_mult = scale_multiplier(source_file_count)

    per_principle = _score_all_principles(
        evidence.get("principles", {}), mode, scale_mult, files_read,
    )
    overall = _weighted_overall(per_principle, mode)

    return ScoringResult(
        repository=evidence.get("repository", ""),
        discipline=evidence.get("discipline", ""),
        date=evidence.get("date", ""),
        mode=mode,
        principles=per_principle,
        overall=overall,
        scale=ScaleInfo(
            tier=SCALE_TIER_NAMES.get(scale_mult, "Small"),
            multiplier=scale_mult,
            files_read=files_read,
        ),
    )


def score_evidence(evidence: Evidence, mode: str = "numerical") -> ScoringResult:
    """Score Evidence using the scoring engine."""
    ev_dict = evidence.to_evidence_dict()
    return run_scoring(ev_dict, mode=mode)
