"""Tests for the live rescore service."""
from quodeq.core.types.finding import Finding, Totals, SeverityTally
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult

from quodeq.services.rescore import rescore_dimensions


def _make_violation(principle="P1", severity="major", req="R1", file="a.py", line=1, reason="bug"):
    return Finding(principle=principle, severity=severity, req=req, file=file, line=line, reason=reason)


def _make_compliance(principle="P1", req="R1", file="a.py", line=10, reason="ok"):
    return Finding(principle=principle, req=req, file=file, line=line, reason=reason)


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
