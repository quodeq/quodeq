"""compute_principle_grade: thin evidence is scored and marked, classes pin severity."""
from __future__ import annotations

from quodeq.core.scoring.projector_scoring import PrincipleGradeScale, compute_principle_grade

from tests.core._projector_scoring_fixtures import _f


def test_single_violation_is_scored_with_low_confidence() -> None:
    result = compute_principle_grade(principle_id="P1", findings=[_f("R1", "P1", severity="critical")], compliance=[])
    assert result["grade"] != "Insufficient" and result["score"] is not None
    assert result["confidence"] == "low" and result["observation"] > 0
    assert result["finding_count"] == 1


def test_nothing_at_all_is_insufficient() -> None:
    result = compute_principle_grade(principle_id="P1", findings=[], compliance=[], dismissed_count=2)
    assert (result["grade"], result["score"], result["dismissed_count"]) == ("Insufficient", None, 2)


def test_unknown_project_size_scores_like_the_unspread_formula() -> None:
    findings = [_f("R1", "P1", severity="major", file=f"f{i}.py") for i in range(30)]
    spread_on = compute_principle_grade(principle_id="P1", findings=findings, compliance=[], scale=PrincipleGradeScale(source_file_count=100))["score"]
    spread_off = compute_principle_grade(principle_id="P1", findings=findings, compliance=[], scale=PrincipleGradeScale(source_file_count=0))["score"]
    assert spread_off > spread_on
