"""Regression: partial taxonomy coverage must not drop untagged violations.

A real quodeq self-scan scored the Modularity principle 9.7/Exemplary while it
held 2 critical and 22 major violations. Root cause: the scoring tally enters
"taxonomy mode" as soon as *any* one violation carries a ``vt`` tag
(``evidence_has_taxonomy``), and ``tally_types_by_taxonomy`` then drops every
violation lacking a ``vt`` (``_tally_types(..., skip_empty=True)``). With only 1
of 80 violations tagged, 79 of them -- including both criticals -- vanished from
the score.

The intended behaviour: a ``vt`` tag is a per-finding grouping key, not a
per-principle mode switch. A tagged finding groups by its ``vt``; an untagged
finding falls back to grouping by ``reason``. Nothing is ever dropped, so the
score is continuous across tag coverage (0 tags and 1 tag score the same; full
coverage just groups more precisely).
"""
from __future__ import annotations

from quodeq.core.scoring.principle import compute_tallies
from quodeq.core.types.finding import Finding
from quodeq.core.scoring.projector_scoring import PrincipleGradeScale, compute_principle_grade


def _v(severity: str, reason: str, vt: str | None = None) -> dict:
    item = {"severity": severity, "reason": reason}
    if vt:
        item["vt"] = vt
    return item


def test_partial_taxonomy_keeps_untagged_violations_in_tally():
    """One tagged minor must not erase two untagged criticals from the tally."""
    violations = [
        _v("minor", "function has too many parameters", vt="excessive-parameters"),
        _v("critical", "incorrect function call signature"),
        _v("critical", "syntax error in jsx closing tag"),
        _v("major", "circular dependency between modules"),
    ]

    vt_counts, _compliance_counts, _used_taxonomy = compute_tallies(violations, [])

    # The bug produced {'critical': 0, 'major': 0, 'minor': 1}: the lone tag
    # flipped the principle into taxonomy mode and skip_empty dropped the rest.
    assert vt_counts["critical"] == 2  # two distinct untagged criticals (by reason)
    assert vt_counts["major"] == 1
    assert vt_counts["minor"] == 1     # the one tagged minor (by vt)


def _f(severity: str, reason: str, vt: str | None = None, file: str = "a.py") -> Finding:
    return Finding(
        practice_id="Modularity", verdict="violation", file=file, line=1,
        end_line=1, title="t", reason=reason, snippet="s", severity=severity,
        cwe=None, req="R1", req_refs=[], context="", dimension="maintainability",
        violation_type=vt, scope="", confidence=100,
    )


_PROJECT_FILES = 100  # the file spread acts only when the project size is known


def _grade(findings: list[Finding]) -> dict:
    return compute_principle_grade(
        principle_id="Modularity", findings=findings, compliance=[],
        scale=PrincipleGradeScale(source_file_count=_PROJECT_FILES),
    )


def test_partial_taxonomy_does_not_inflate_principle_grade():
    """Reproduces the self-scan: 1 tagged minor + 2 critical + 22 major + 55 minor.

    The scenario is one rule (R1) across 80 files of a 100-file project. Before
    the fix this scored 9.7/Exemplary because the untagged criticals and majors
    were dropped; with them counted it must be a low, non-Exemplary grade.
    """
    findings = (
        [_f("minor", "too many parameters", vt="excessive-parameters", file="f0.py")]
        + [_f("critical", f"critical defect {i}", file=f"f{1 + i}.py") for i in range(2)]
        + [_f("major", f"major defect {i}", file=f"f{3 + i}.py") for i in range(22)]
        + [_f("minor", f"minor defect {i}", file=f"f{25 + i}.py") for i in range(55)]
    )

    result = _grade(findings)

    assert result["finding_count"] == 80
    assert result["grade"] != "Exemplary"
    assert result["score"] < 7.0
    # The criticals are not dropped: removing them must raise the score.
    without_criticals = _grade([f for f in findings if f.severity != "critical"])
    assert without_criticals["score"] > result["score"]
