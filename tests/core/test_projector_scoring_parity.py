"""Parity tests: the projector's scoring vs the core engine.

Parity is core engine vs projector: the reference side runs the CLI's
``core.scoring.engine.run_scoring`` over evidence-dict principles built from
the same findings (``score_all_principles`` then ``weighted_overall``); the
projector side runs ``compute_principle_grade`` + ``compute_dimension_score``.
Both build requirement masses with the same primitives, so parity is
structural and these tests guard against drift. Thin evidence is scored (and
marked low confidence) by both rather than gated to Insufficient.

The wide test is parametrized over project size (unknown, small, large),
rules hit in several files at mixed severities, and a principle whose every
finding was dismissed (it stays in the
engine's evidence, empty). Per principle the score and the confidence must
match; per dimension the score must match. The projector's ``None``
confidence on an Insufficient principle reads ``low`` in the engine, as in
the legacy rescore.

Shared `_f` finding builder lives in tests/core/_projector_scoring_fixtures.py.
"""
from __future__ import annotations

import pytest

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.engine import run_scoring
from quodeq.core.scoring.internals import finding_to_scoring_dict
from quodeq.core.scoring.overall import MODE_NUMERICAL
from quodeq.core.scoring.projector_scoring import (
    PrincipleGradeScale,
    compute_dimension_score,
    compute_principle_grade,
)
from quodeq.core.types.scoring import ConfidenceLevel

from tests.core._projector_scoring_fixtures import _f


def _evidence_principles(violations, compliance) -> dict:
    """Evidence-dict principles, the shape the CLI engine scores."""
    principles: dict = {}
    for key, rows in (("violations", violations), ("compliance", compliance)):
        for f in rows:
            principles.setdefault(f.practice_id, {"violations": [], "compliance": []})[key].append(
                finding_to_scoring_dict(f),
            )
    for pdata in principles.values():
        pdata["metrics"] = {"confidence_level": classify_confidence_level(
            len(pdata["violations"]), len(pdata["compliance"]),
        )}
    return principles


def _legacy_dim_score(violations, compliance) -> float | None:
    """The dimension score the core engine gives the same findings."""
    evidence = {"source_file_count": 0, "files_read": 0,
                "principles": _evidence_principles(violations, compliance)}
    return run_scoring(evidence, MODE_NUMERICAL).overall.weighted_score


def _new_dim_score(violations, compliance) -> float | None:
    """Compute the same dimension score via projector_scoring."""
    violations_by: dict = {}
    for v in violations:
        violations_by.setdefault(v.practice_id, []).append(v)
    comp_by: dict = {}
    for c in compliance:
        comp_by.setdefault(c.practice_id, []).append(c)
    p_grades = [
        compute_principle_grade(
            principle_id=p,
            findings=violations_by.get(p, []),
            compliance=comp_by.get(p, []),
            scale=PrincipleGradeScale(source_file_count=0),
        )
        for p in sorted(set(violations_by) | set(comp_by))
    ]
    return compute_dimension_score(dimension="Security", principle_grades=p_grades)["score"]


def test_parity_single_principle_sufficient_violations() -> None:
    """5 same-severity violations clears the medium-confidence floor."""
    violations = [_f(f"R{i}", "P1", "high") for i in range(5)]
    compliance = []
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_single_principle_violation_and_compliance() -> None:
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_multiple_principles() -> None:
    """Each principle has enough findings to clear the confidence floor."""
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)] \
        + [_f(f"W{i}", "P2", "critical") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)] \
        + [_f(f"D{i}", "P2", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_thin_evidence_is_scored_in_both() -> None:
    """One finding is scored (not gated) and marked low confidence by both engines."""
    violations = [_f("R1", "P1", "critical")]
    legacy = _legacy_dim_score(violations, [])
    p_grade = compute_principle_grade(principle_id="P1", findings=violations, compliance=[])
    assert p_grade["grade"] != "Insufficient" and p_grade["confidence"] == "low"
    new_dim = compute_dimension_score(dimension="Security", principle_grades=[p_grade])
    assert new_dim["score"] == legacy
    assert new_dim["confidence"] == "low"


def test_dimension_score_weighs_by_observation_and_flags_thin_dimensions() -> None:
    heavy = {"principle_id": "a", "score": 4.6, "grade": "Poor", "observation": 400.0, "confidence": "high"}
    thin = {"principle_id": "b", "score": 10.0, "grade": "Exemplary", "observation": 1.3, "confidence": "low"}
    out = compute_dimension_score(dimension="Security", principle_grades=[heavy, thin])
    assert 4.6 <= out["score"] <= 4.7 and out["confidence"] is None
    thin_only = compute_dimension_score(dimension="Security", principle_grades=[thin, dict(thin, principle_id="c")])
    assert thin_only["confidence"] == "low"


_EMPTY = "P-dismissed"


def _rule(req: str, principle: str, severities: list[str], verdict: str = "violation") -> list:
    return [_f(req, principle, sev, verdict=verdict, file=f"{req}-f{i}.py") for i, sev in enumerate(severities)]


_VIOLATIONS = (
    _rule("R-A", "P1", ["minor", "major", "minor", "minor"])
    + _rule("R-B", "P1", ["critical", "major"])
    + _rule("R-C", "P2", ["major"] * 6 + ["critical"] * 2)
    + _rule("R-D", "P3", ["minor"])
    + _rule("R-E", "P4", ["critical"])
)
_COMPLIANCE = (
    _rule("C-A", "P1", ["minor"] * 3, verdict="compliance")
    + _rule("C-B", "P3", ["minor"] * 9, verdict="compliance")
)


def _by_principle(findings) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in findings:
        out.setdefault(f.practice_id, []).append(f)
    return out


def _engine(source_file_count: int):
    violations, compliance = _by_principle(_VIOLATIONS), _by_principle(_COMPLIANCE)
    principles = {_EMPTY: {"violations": [], "compliance": [],
                           "metrics": {"confidence_level": classify_confidence_level(0, 0)}}}
    for key in set(violations) | set(compliance):
        v = [finding_to_scoring_dict(x) for x in violations.get(key, [])]
        c = [finding_to_scoring_dict(x) for x in compliance.get(key, [])]
        principles[key] = {"violations": v, "compliance": c, "metrics": {
            "confidence_level": classify_confidence_level(len(v), len(c), source_file_count=source_file_count)}}
    evidence = {"source_file_count": source_file_count, "files_read": 0, "principles": principles}
    return run_scoring(evidence, MODE_NUMERICAL)


def _projector(source_file_count: int):
    violations, compliance = _by_principle(_VIOLATIONS), _by_principle(_COMPLIANCE)
    scale = PrincipleGradeScale(source_file_count=source_file_count)
    grades = [
        compute_principle_grade(principle_id=key, findings=violations.get(key, []),
                                compliance=compliance.get(key, []), scale=scale)
        for key in sorted(set(violations) | set(compliance) | {_EMPTY})
    ]
    return grades, compute_dimension_score(dimension="Security", principle_grades=grades)


@pytest.mark.parametrize("source_file_count", [0, 100, 3000])
def test_engine_and_projector_agree(source_file_count) -> None:
    engine = _engine(source_file_count)
    grades, dimension = _projector(source_file_count)
    for grade in grades:
        core = engine.principles[grade["principle_id"]]
        assert core.final_score == grade["score"], grade["principle_id"]
        assert core.grade == grade["grade"], grade["principle_id"]
        assert core.confidence_level == (grade["confidence"] or ConfidenceLevel.LOW), grade["principle_id"]
    assert engine.principles[_EMPTY].grade == Grade.INSUFFICIENT
    assert engine.overall.weighted_score == dimension["score"]
    assert engine.overall.grade == dimension["grade"]


def test_size_changes_the_numbers() -> None:
    """Guard against a vacuous parametrization: the size axis really moves the score."""
    scores = {n: _projector(n)[1]["score"] for n in (0, 100, 3000)}
    assert len(set(scores.values())) > 1
    confidences = {g["confidence"] for g in _projector(100)[0]}
    assert {"low", "medium", "high"} <= confidences
