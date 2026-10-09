"""Principle-level scoring logic (internal module)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from quodeq.core.types import ConfidenceLevel, PrincipleScore
from quodeq.core.evidence.model import DEFAULT_WEIGHT
from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.overall import MODE_NUMERICAL
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.scoring.internals import (
    build_deductions,
    compliance_dampening,
    confidence_interval_for,
    count_grade_drops,
    drop_grade,
    evidence_has_taxonomy,
    principle_stages,
    score_to_grade_label,
    tally_types,
)


@dataclass(frozen=True)
class _PrincipleContext:
    """Scoring context for a single principle."""
    key: str
    pdata: dict
    pct: float
    vt_counts: dict[str, int]
    ct_counts: dict[str, int]
    using_taxonomy: bool
    conf_level: str
    ci: dict
    scale_mult: int
    source_file_count: int = 0
    classes: Mapping[str, str] = field(default_factory=dict)


def compute_tallies(
    violations: list, compliance: list,
) -> tuple[dict[str, int], dict[str, int], bool]:
    """Tally distinct violation and compliance types per severity.

    Each finding is grouped by its ``req`` requirement code, then by its
    ``vt`` tag, then by its ``reason`` (see ``tally_types``), so a partly
    tagged principle still counts all of its findings (including untagged
    criticals). ``using_taxonomy`` is reported (any finding carries a ``vt``)
    for display only; it does not change which findings are counted.
    """
    using_taxonomy = evidence_has_taxonomy(violations)
    vt_counts = tally_types(violations)
    ct_counts = tally_types(compliance)
    return vt_counts, ct_counts, using_taxonomy


def _base_kwargs(ctx: _PrincipleContext) -> dict:
    """Common keyword arguments shared by both scoring modes."""
    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }


def _score_numerical(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,
) -> PrincipleScore:
    """Score a single principle in numerical mode. Thin evidence is scored and marked, not gated."""
    kwargs = _base_kwargs(ctx)
    rows = requirement_rows(ctx.pdata.get("violations", []), ctx.pdata.get("compliance", []))
    mass = principle_mass(rows, ctx.source_file_count, ctx.classes, params=params)
    base, lift, _raw, final = principle_stages(mass, params=params)
    return PrincipleScore(
        **kwargs, base_score=round(base, 1),
        deductions=build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult),
        dampening_multiplier=lift, final_score=final,
        grade=score_to_grade_label(final, params=params),
        observation=mass.observation, violation_mass=mass.violation_mass,
        compliance_mass=mass.compliance_mass,
    )


def _score_graded(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,  # noqa: ARG001
) -> PrincipleScore:
    """Score a single principle in non-numerical (graded) mode.

    Accepts params only for scorer-signature symmetry with
    ``_score_numerical``; the legacy graded ladder is not user-tunable.
    """
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == ConfidenceLevel.LOW:
        return PrincipleScore(
            **kwargs, base_grade=Grade.INSUFFICIENT, severity_drops=0,
            grade=Grade.INSUFFICIENT,
        )
    drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    # Graded mode is the only reader of the legacy dampening multiplier.
    dampening = compliance_dampening(ctx.ct_counts, ctx.vt_counts)
    return PrincipleScore(
        **kwargs, base_grade=Grade.EXEMPLARY, severity_drops=drops,
        dampening_multiplier=dampening,
        grade=drop_grade(Grade.EXEMPLARY, int(drops * dampening)),
    )


def _build_context(
    key: str, pdata: dict, scale_mult: int, files_read: int,
    source_file_count: int = 0, classes: Mapping[str, str] | None = None,
) -> _PrincipleContext:
    """Build scoring context for a single principle from its evidence data."""
    metrics = pdata.get("metrics", {})
    pct = metrics.get("compliance_percentage", 0.0)
    conf_level = metrics.get("confidence_level", ConfidenceLevel.MEDIUM)
    vt_counts, ct_counts, using_taxonomy = compute_tallies(
        pdata.get("violations", []), pdata.get("compliance", []),
    )
    ci = confidence_interval_for(
        confidence_level=conf_level,
        is_balanced=metrics.get("is_balanced", True),
        total_instances=metrics.get("total_instances", 0),
        files_read=files_read,
    )
    return _PrincipleContext(
        key=key, pdata=pdata, pct=pct, vt_counts=vt_counts,
        ct_counts=ct_counts,
        using_taxonomy=using_taxonomy, conf_level=conf_level, ci=ci,
        scale_mult=scale_mult, source_file_count=source_file_count,
        classes=classes or {},
    )


def score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
    params: ScoringParams = DEFAULT_PARAMS,
    *, source_file_count: int = 0, classes: Mapping[str, str] | None = None,
) -> dict[str, PrincipleScore]:
    """Score every principle and return the per-principle dict."""
    scorer = _score_numerical if mode == MODE_NUMERICAL else _score_graded
    return {
        key: scorer(
            _build_context(key, pdata, scale_mult, files_read, source_file_count, classes),
            params,
        )
        for key, pdata in raw_principles.items()
    }
