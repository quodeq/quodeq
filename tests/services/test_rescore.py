"""Tests for the live rescore service."""
import json

from quodeq.core.types.finding import Finding, Totals, SeverityTally
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult

from quodeq.services.rescore import _rescore_dimension, rescore_dimensions


def _make_violation(practice_id="P1", severity="major", req="R1", file="a.py", line=1, reason="bug"):
    return Finding(practice_id=practice_id, severity=severity, req=req, file=file, line=line, reason=reason)


def _make_compliance(practice_id="P1", req="R1", file="a.py", line=10, reason="ok"):
    return Finding(practice_id=practice_id, req=req, file=file, line=line, reason=reason)


def _make_dimension(
    name="Reliability", violations=None, compliance=None,
    source_file_count=100, files_read=None,
):
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
        files_read=files_read,
    )


def test_rescore_dimension_matches_string_line():
    """A finding whose line is a string ("10") is still suppressed by a dismissal
    stored with an int line (10). dismissed_keys stores int(line); Finding.line is
    typed int|str|None, so the read side must coerce too or a string-lined finding
    never matches its own dismissal."""
    dim = _make_dimension(violations=[_make_violation(req="R1", file="a.py", line="10")])
    rescored = _rescore_dimension(dim, {("R1", "a.py", 10)})
    assert rescored.violations == []  # string-lined finding filtered out


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


def test_rescore_dimension_uses_evidence_when_run_dir_given(tmp_path):
    """When run_dir has `<dim>_evidence.jsonl`, the score comes from the
    evidence rescorer (Task 5), not the in-place legacy formula.
    """
    ev = tmp_path / "evidence"
    ev.mkdir()
    lines = [
        {"schema_version": 1, "req": "R-1", "t": "violation", "file": "a.kt",
         "line": 10, "severity": "critical", "w": "t", "reason": "r1",
         "vt": "VT-X", "p": "Modularity", "d": "maintainability"},
        {"schema_version": 1, "req": "R-2", "t": "violation", "file": "b.kt",
         "line": 2, "severity": "minor", "w": "t", "reason": "r2",
         "vt": "", "p": "Modularity", "d": "maintainability"},
        {"schema_version": 1, "req": "C-1", "t": "compliance", "file": "a.kt",
         "line": 1, "severity": "minor", "w": "t", "reason": "c1",
         "vt": "", "p": "Modularity", "d": "maintainability"},
    ]
    (ev / "maintainability_evidence.jsonl").write_text(
        "\n".join(json.dumps(l) for l in lines) + "\n")

    dim = _make_dimension(
        name="maintainability",
        violations=[
            _make_violation(req="R-1", file="a.kt", line=10, severity="critical",
                             practice_id="Modularity"),
            _make_violation(req="R-2", file="b.kt", line=2, severity="minor",
                             practice_id="Modularity"),
        ],
        source_file_count=1000, files_read=10,
    )
    out = _rescore_dimension(dim, {("R-1", "a.kt", 10)}, set(), run_dir=tmp_path)

    # Violations list is filtered as before...
    assert [v.req for v in out.violations] == ["R-2"]

    # ...and the SCORE equals the evidence-engine score of the remaining set,
    # not the legacy report-JSON formula.
    from quodeq.core.scoring.params import DEFAULT_PARAMS
    from quodeq.services.evidence_rescore import score_dimension_from_evidence

    expected = score_dimension_from_evidence(
        tmp_path, "maintainability", dismissed={("R-1", "a.kt", 10)}, deleted=set(),
        source_file_count=1000, files_read=10, params=DEFAULT_PARAMS,
    )
    assert out.overall_score == (
        f"{expected.overall.weighted_score}/10"
        if expected.overall.weighted_score is not None else None
    )


def test_rescore_dimension_without_run_dir_keeps_legacy_fallback():
    """Passing run_dir=None explicitly must produce exactly the same result
    as omitting run_dir altogether -- the legacy in-place formula, unchanged.

    Reuses test_rescore_dismissing_violation_changes_score's setup (dismissing
    a critical violation should raise the score) and locks in that omitting
    run_dir and passing run_dir=None are equivalent code paths.
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
    dismissed = {("R1", "a.py", 1)}

    omitted = _rescore_dimension(dim, dismissed)
    explicit_none = _rescore_dimension(dim, dismissed, run_dir=None)

    assert explicit_none == omitted
    assert explicit_none.overall_score is not None

    result_omitted = rescore_dimensions([dim], dismissed_keys=dismissed)
    result_explicit_none = rescore_dimensions([dim], dismissed_keys=dismissed, run_dir=None)
    assert result_explicit_none == result_omitted


def test_untouched_dimension_passthrough_even_with_run_dir(tmp_path):
    """The early-return passthrough (no findings filtered -> no rescoring)
    must still short-circuit before any evidence lookup, even when a run_dir
    is supplied.
    """
    dim = _make_dimension(violations=[_make_violation(req="R-9", file="z.kt", line=1)])
    out = _rescore_dimension(dim, {("OTHER", "x.kt", 5)}, set(), run_dir=tmp_path)
    assert out is dim  # early return preserved: no filtering -> no rescoring
