"""Legacy in-place rescoring: recompute a dimension's grade from its
filtered Finding lists when no run-evidence basis is available.

Split out of rescore.py. This is the fallback path only --
_rescore_from_evidence in rescore.py is preferred whenever a run's
`<dim>_evidence.jsonl` is available.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.internals import finding_to_scoring_dict, principle_score_and_grade
from quodeq.core.scoring.mass import principle_mass, requirement_rows
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.scoring import ConfidenceLevel, PrincipleScore


def _score_principle(
    violations: list[Finding], compliance: list[Finding],
    *, source_file_count: int = 0, scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS, classes: Mapping[str, str] | None = None,
) -> tuple[float | None, str, str | None, float]:
    """Score a single principle from its filtered violations and compliance lists.

    Scores on the same spread masses the CLI engine uses, so the
    rescore-after-dismiss path agrees with the CLI's original grade and the
    dashboard, the dim-detail view and the CLI's JSON report show one number.
    Insufficient only when the principle has no instances at all.

    Returns (final_score, grade, confidence, observation).
    """
    if not violations and not compliance:
        return None, Grade.INSUFFICIENT, None, 0.0
    confidence = classify_confidence_level(
        len(violations), len(compliance),
        scale_multiplier=scale_multiplier,
        source_file_count=source_file_count,
    )
    rows = requirement_rows([finding_to_scoring_dict(v) for v in violations],
                            [finding_to_scoring_dict(c) for c in compliance])
    mass = principle_mass(rows, source_file_count, classes or {}, params=params)
    final, grade = principle_score_and_grade(mass, params=params)
    return final, grade, str(confidence), mass.observation


def group_by_principle(
    findings: list[Finding],
) -> dict[str, list[Finding]]:
    """Group a list of findings by their principle name."""
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.practice_id or "unknown", []).append(f)
    return groups


def score_all_principles(
    principles_violations: dict[str, list[Finding]],
    principles_compliance: dict[str, list[Finding]],
    *,
    source_file_count: int = 0,
    scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
    classes: Mapping[str, str] | None = None,
) -> tuple[dict[str, PrincipleScore], list[PrincipleGrade]]:
    """Score each principle and return (scores_dict, grades_list)."""
    all_principle_names = set(principles_violations) | set(principles_compliance)
    principle_scores: dict[str, PrincipleScore] = {}
    principle_grades: list[PrincipleGrade] = []

    for name in sorted(all_principle_names):
        p_violations = principles_violations.get(name, [])
        p_compliance = principles_compliance.get(name, [])
        final_score, grade, confidence, observation = _score_principle(
            p_violations, p_compliance,
            source_file_count=source_file_count,
            scale_multiplier=scale_multiplier,
            params=params, classes=classes,
        )
        score_str = f"{final_score}/10" if final_score is not None else None

        principle_scores[name] = PrincipleScore(
            display_name=name, weight="1", final_score=final_score, grade=grade,
            confidence_level=confidence or ConfidenceLevel.LOW, observation=observation,
        )
        principle_grades.append(PrincipleGrade(principle=name, score=score_str, grade=grade))
    return principle_scores, principle_grades
