"""A dismissal never lowers its dimension: the dismissed file stays observed."""
from __future__ import annotations

from quodeq.core.scoring.projector_scoring import (
    PrincipleGradeScale,
    compute_dimension_score,
    compute_principle_grade,
)
from quodeq.core.types.finding import Finding

SCALE = PrincipleGradeScale(source_file_count=200)


def _v(req: str, file: str, severity: str = "major") -> Finding:
    return Finding(practice_id="P", file=file, line=1, req=req, severity=severity, verdict="violation")


def _c(req: str, file: str) -> Finding:
    return Finding(practice_id="P", file=file, line=1, req=req, verdict="compliance")


def _dimension(clean_violations: list[Finding], dismissed: list[Finding]) -> float:
    # "clean": one minor rule broken in one file, followed in forty; "noisy": many majors.
    clean = compute_principle_grade(
        principle_id="clean", findings=clean_violations,
        compliance=[_c("C-1", f"c{i}") for i in range(40)], dismissed=dismissed, scale=SCALE)
    noisy = compute_principle_grade(
        principle_id="noisy", findings=[_v(f"N-{i}", f"n{i}") for i in range(12)],
        compliance=[], scale=SCALE)
    return compute_dimension_score(dimension="d", principle_grades=[clean, noisy])["score"]


def test_dismissing_in_a_strong_principle_does_not_lower_the_dimension():
    finding = _v("C-2", "x.py", "minor")
    before = _dimension([finding, _v("C-3", "y.py", "minor")], [])
    after = _dimension([_v("C-3", "y.py", "minor")], [finding])
    assert after >= before


def test_the_dismissed_count_is_reported():
    grade = compute_principle_grade(
        principle_id="p", findings=[_v("R-1", "a.py")], compliance=[], dismissed=[_v("R-1", "b.py")], scale=SCALE)
    assert grade["dismissed_count"] == 1
