from __future__ import annotations

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.grade_explain import _explain_one
from quodeq.services.wiring import GradeInputs

from tests.core._projector_scoring_fixtures import _f


def test_explain_one_scores_thin_principles_and_lists_rules() -> None:
    key = ("Security", "P1")
    inputs = GradeInputs(
        violations_by={key: [_f("S-INT-2", "P1", severity="minor", file="a.py")]},
        compliance_by={key: [_f("S-INT-1", "P1", severity="minor", verdict="compliance", file="b.py")]},
        dismissed_by={}, source_file_count=1000,
    )
    out = _explain_one(inputs, key, DEFAULT_PARAMS)
    assert out["insufficient"] is False and out["confidence"] == "low" and out["files"] == 1000
    first = out["stages"]["requirements"][0]
    assert first["req"] == "S-INT-2" and first["filesAtLeastMinor"] == 1 and "class" not in first


def test_explain_one_with_nothing_is_insufficient() -> None:
    inputs = GradeInputs(violations_by={}, compliance_by={}, dismissed_by={}, source_file_count=0)
    out = _explain_one(inputs, ("Security", "P1"), DEFAULT_PARAMS)
    assert out["insufficient"] is True and out["stages"] is None
