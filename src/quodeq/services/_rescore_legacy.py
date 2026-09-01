"""Legacy in-place rescoring: recompute a dimension's grade from its
filtered Finding lists when no run-evidence basis is available.

Split out of rescore.py (Task 12). This is the fallback path only --
_rescore_from_evidence in rescore.py is preferred whenever a run's
`<dim>_evidence.jsonl` is available.
"""
from __future__ import annotations

from typing import Any

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.internals import (
    compliance_lift,
    score_to_grade_label,
    severity_grade_floor,
    violation_base,
    violation_ceiling,
)
from quodeq.core.scoring.engine import compute_tallies
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.scoring import PrincipleScore


def _finding_to_dict(f: Finding) -> dict[str, Any]:
    """Convert a Finding dataclass to the dict format scoring internals expect.

    Only includes 'vt' when the finding has an explicit violation_type, so
    ``evidence_has_taxonomy()`` selects the same mode (taxonomy vs reason)
    that the original evaluation used.
    """
    d: dict[str, Any] = {
        "severity": f.severity or "minor",
        "reason": f.reason or "",
    }
    if f.violation_type:
        d["vt"] = f.violation_type
    return d


def _score_principle(
    violations: list[Finding], compliance: list[Finding],
    *, source_file_count: int = 0, scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float | None, str]:
    """Score a single principle from its filtered violations and compliance lists.

    Applies the same confidence-level Insufficient rule the CLI engine
    uses (see ``core.evidence.model.classify_confidence_level``) — keeps
    the rescore-after-dismiss path in sync with the CLI's original grade
    so the dashboard, the dim-detail view, and the CLI's JSON report all
    agree on the same number.

    Returns (final_score, grade).
    """
    v_dicts = [_finding_to_dict(v) for v in violations]
    c_dicts = [_finding_to_dict(c) for c in compliance]
    vt_counts, ct_counts, _using_taxonomy = compute_tallies(v_dicts, c_dicts)
    if not vt_counts and not ct_counts:
        return None, "Insufficient"

    confidence = classify_confidence_level(
        len(violations), len(compliance),
        scale_multiplier=scale_multiplier,
        source_file_count=source_file_count,
    )
    if confidence == "low":
        return None, "Insufficient"

    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    # Floor first, ceiling last -- see the note in core/scoring/projector_scoring.py.
    # Keep byte-identical with it.
    final = min(ceil, max(floor, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    return final, grade


def _group_by_principle(
    findings: list[Finding],
) -> dict[str, list[Finding]]:
    """Group a list of findings by their principle name."""
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.practice_id or "unknown", []).append(f)
    return groups


def _score_all_principles(
    principles_violations: dict[str, list[Finding]],
    principles_compliance: dict[str, list[Finding]],
    *,
    source_file_count: int = 0,
    scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[dict[str, PrincipleScore], list[PrincipleGrade]]:
    """Score each principle and return (scores_dict, grades_list)."""
    all_principle_names = set(principles_violations) | set(principles_compliance)
    principle_scores: dict[str, PrincipleScore] = {}
    principle_grades: list[PrincipleGrade] = []

    for name in sorted(all_principle_names):
        p_violations = principles_violations.get(name, [])
        p_compliance = principles_compliance.get(name, [])
        final_score, grade = _score_principle(
            p_violations, p_compliance,
            source_file_count=source_file_count,
            scale_multiplier=scale_multiplier,
            params=params,
        )
        score_str = f"{final_score}/10" if final_score is not None else None

        principle_scores[name] = PrincipleScore(
            display_name=name, weight="1", final_score=final_score, grade=grade,
        )
        principle_grades.append(PrincipleGrade(principle=name, score=score_str, grade=grade))
    return principle_scores, principle_grades
