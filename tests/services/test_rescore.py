"""Tests for the live rescore service."""
from quodeq.core.types.finding import Finding, Totals, SeverityTally
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult

from quodeq.services.rescore import rescore_dimensions


def _make_violation(practice_id="P1", severity="major", req="R1", file="a.py", line=1, reason="bug"):
    return Finding(practice_id=practice_id, severity=severity, req=req, file=file, line=line, reason=reason)


def _make_compliance(practice_id="P1", req="R1", file="a.py", line=10, reason="ok"):
    return Finding(practice_id=practice_id, req=req, file=file, line=line, reason=reason)


def _make_dimension(name="Reliability", violations=None, compliance=None, source_file_count=100):
    violations = violations or []
    compliance = compliance or []
    return DimensionResult(
        dimension=name,
        violations=violations,
        compliance=compliance,
        overall_score="5.0/10",
        overall_grade="Adequate",
        principles=[PrincipleGrade(principle="P1", score="5.0/10", grade="Adequate")],
        totals=Totals(
            violation_count=len(violations),
            compliance_count=len(compliance),
            severity=SeverityTally(
                critical=sum(1 for v in violations if v.severity == "critical"),
                major=sum(1 for v in violations if v.severity == "major"),
                minor=sum(1 for v in violations if v.severity == "minor"),
            ),
        ),
        source_file_count=source_file_count,
    )


def test_rescore_no_dismissals_returns_rescored_data():
    """With no dismissed keys, rescore should still return valid rescored dimensions."""
    dim = _make_dimension(
        violations=[_make_violation(severity="major")],
        compliance=[_make_compliance()],
    )
    result = rescore_dimensions([dim], dismissed_keys=set())
    assert len(result["dimensions"]) == 1
    assert result["dimensions"][0]["overallScore"] is not None
    assert result["dimensions"][0]["overallGrade"] is not None
    assert result["summary"] is not None
    assert result["summary"]["overallGrade"] is not None


def test_rescore_dismissing_violation_changes_score():
    """Dismissing a violation should produce a different (better) score.

    Uses enough findings (>= medium threshold) to clear the
    confidence-level floor; otherwise both before/after scores collapse
    to ``Insufficient`` and the comparison is meaningless.
    """
    v1 = _make_violation(severity="critical", req="R1", file="a.py", line=1, reason="null deref")
    extra_violations = [
        _make_violation(severity="major", req=f"R{i}", file=f"f{i}.py", line=10)
        for i in range(2, 6)
    ]
    compliance = [
        _make_compliance(req=f"C{i}", file=f"c{i}.py", line=20)
        for i in range(5)
    ]
    dim = _make_dimension(violations=[v1, *extra_violations], compliance=compliance)

    result_all = rescore_dimensions([dim], dismissed_keys=set())
    result_dismissed = rescore_dimensions([dim], dismissed_keys={("R1", "a.py", 1)})

    score_all = result_all["dimensions"][0]["overallScore"]
    score_dismissed = result_dismissed["dimensions"][0]["overallScore"]

    assert score_dismissed != score_all
    num_all = float(score_all.split("/")[0])
    num_dismissed = float(score_dismissed.split("/")[0])
    assert num_dismissed > num_all, (
        f"dismissing the critical should raise the score; "
        f"got {num_all} → {num_dismissed}"
    )


def test_rescore_dismiss_all_violations():
    """Dismissing all violations should yield a high score."""
    v1 = _make_violation(severity="major", req="R1", file="a.py", line=1)
    dim = _make_dimension(violations=[v1], compliance=[_make_compliance()])

    result = rescore_dimensions([dim], dismissed_keys={("R1", "a.py", 1)})
    dim_result = result["dimensions"][0]

    # No violations left — score should be high
    assert dim_result["totals"]["violationCount"] == 0


def test_rescore_summary_reflects_dimension_changes():
    """Run-level summary should reflect rescored dimension scores."""
    v1 = _make_violation(severity="critical", req="R1", file="a.py", line=1)
    dim1 = _make_dimension(name="Reliability", violations=[v1], compliance=[_make_compliance()])
    dim2 = _make_dimension(name="Security", violations=[], compliance=[_make_compliance()])

    result = rescore_dimensions([dim1, dim2], dismissed_keys=set())
    summary = result["summary"]
    assert summary["dimensionsCount"] == 2
    assert summary["overallGrade"] is not None
