from __future__ import annotations

from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from quodeq.core.scoring.engine import score_evidence

from tests.engine.conftest import make_evidence_with_confidence

_TEST_FILE = "a.ts"
_TEST_SNIPPET = "eval(x)"


def _make_evidence(violations=None, compliance=None) -> Evidence:
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
        violations=violations or [
            {"file": _TEST_FILE, "line": 1, "snippet": _TEST_SNIPPET, "reason": "injection", "severity": "high", "vt": "code-injection"},
        ],
        compliance=compliance or [
            {"file": "b.ts", "line": 2, "snippet": "JSON.parse(x)", "reason": "safe"},
            {"file": "c.ts", "line": 3, "snippet": "JSON.parse(y)", "reason": "safe"},
        ],
        metrics={
            "total_instances": 3,
            "compliant": 2,
            "violating": 1,
            "compliance_percentage": 66.7,
            "confidence_level": "medium",
            "is_balanced": True,
        },
    )
    return Evidence(
        repository="test-repo",
        language="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={"ts-001": pe},
    )


def test_numerical_scoring():
    ev = _make_evidence()
    scores = score_evidence(ev, mode="numerical")
    assert scores.principles is not None
    assert scores.overall is not None
    assert scores.mode == "numerical"
    ts001 = scores.principles.get("ts-001")
    assert ts001 is not None
    assert ts001.final_score is not None
    assert isinstance(ts001.final_score, (int, float))


def test_non_numerical_grading():
    ev = _make_evidence()
    scores = score_evidence(ev, mode="non-numerical")
    assert scores.mode == "non-numerical"
    ts001 = scores.principles.get("ts-001")
    assert ts001 is not None
    assert ts001.grade is not None


def test_empty_evidence():
    ev = Evidence(
        repository="test",
        language="typescript",
        date="2026-03-03",
        source_file_count=0,
        files_read=0,
        coverage_pct=0.0,
    )
    scores = score_evidence(ev)
    assert scores.principles == {}
    assert scores.overall.weighted_score == 0.0


def test_scoring_structure():
    """Ensure scoring produces expected structure."""
    ev = _make_evidence()
    scores = score_evidence(ev)
    assert scores.repository is not None
    assert scores.discipline is not None
    assert scores.scale is not None
    assert scores.scale.tier is not None
    assert scores.scale.multiplier is not None


# ---------------------------------------------------------------------------
# Deduction-only scoring model tests
# ---------------------------------------------------------------------------


def test_numerical_low_confidence_returns_insufficient():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.grade == "Insufficient"
    assert ts001.final_score == 0.0


def test_graded_low_confidence_returns_insufficient():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.grade == "Insufficient"


def test_numerical_high_confidence_no_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.base_score == 10
    assert ts001.final_score == 10.0
    assert ts001.grade == "Exemplary"


def test_numerical_high_confidence_with_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", n_violations=2, n_compliance=8,
        violations=[
            {"file": _TEST_FILE, "line": 1, "snippet": _TEST_SNIPPET, "reason": "r", "severity": "critical", "vt": "code-injection"},
            {"file": "b.ts", "line": 2, "snippet": "eval(y)", "reason": "r", "severity": "major", "vt": "unsafe-call"},
        ],
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    # base = 10/(1+0.12*5.5) ≈ 6.0 (1 crit @ 4.0 + 1 major @ 1.5)
    # Compliance carries no vt, but it is no longer dropped: it falls back to
    # grouping by `reason`, so the passing evidence yields a small positive lift
    # above the violation base. (Before the taxonomy-fallback fix this asserted
    # lift == 0.0 / final == 6.0, because untagged compliance was discarded.)
    assert ts001.base_score == 6.0
    assert ts001.dampening_multiplier > 0.0  # untagged compliance now counts (reason fallback)
    assert ts001.final_score == 6.2


def test_graded_high_confidence_no_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.base_grade == "Exemplary"
    assert ts001.grade == "Exemplary"


def test_weighted_overall_excludes_insufficient():
    """A mix of Insufficient and scored principles: overall uses only scored ones."""
    pe_low = PrincipleEvidence(
        practice_id="p-low", display_name="Low Conf", dimension="security",
        severity="high", violations=[], compliance=[],
        metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
    )
    pe_high = PrincipleEvidence(
        practice_id="p-high", display_name="High Conf", dimension="security",
        severity="high",
        violations=[{"file": _TEST_FILE, "line": 1, "snippet": "x", "reason": "r", "severity": "critical", "vt": "vt1"}],
        compliance=[{"file": "b.ts", "line": 2, "snippet": "y", "reason": "r"}] * 9,
        metrics={"total_instances": 10, "compliant": 9, "violating": 1,
                 "compliance_percentage": 90.0, "confidence_level": "high", "is_balanced": True},
    )
    ev = Evidence(
        repository="test", language="ts", date="2026-03-03",
        source_file_count=100, files_read=50, coverage_pct=50.0,
        principles={"p-low": pe_low, "p-high": pe_high},
    )
    scores = score_evidence(ev, mode="numerical")
    assert scores.principles["p-low"].grade == "Insufficient"
    # Overall should reflect only p-high, not be dragged down by p-low
    assert scores.overall.weighted_score == scores.principles["p-high"].final_score


def test_all_insufficient_overall():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    assert scores.overall.grade == "Insufficient"
    assert scores.overall.weighted_score == 0.0


# --- params threading through run_scoring ------------------------------------
import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS


def test_run_scoring_with_strict_params_lowers_scores():
    """The same evidence scores lower when severity weights are raised."""
    from quodeq.core.scoring.engine import run_scoring

    evidence = {
        "repository": "r", "discipline": "d", "date": "2026-06-10",
        "source_file_count": 100, "files_read": 100,
        "principles": {
            "p1": {
                "display_name": "P1", "weight": "1",
                "metrics": {
                    "compliance_percentage": 50.0, "confidence_level": "high",
                    "is_balanced": True, "total_instances": 20,
                },
                "violations": [
                    {"severity": "major", "reason": f"r{i}"} for i in range(5)
                ],
                "compliance": [
                    {"severity": "minor", "reason": f"c{i}"} for i in range(10)
                ],
            },
        },
    }
    default_result = run_scoring(evidence, "numerical")
    strict = dataclasses.replace(
        DEFAULT_PARAMS,
        severity_weight={"critical": 4.0, "major": 5.0, "minor": 0.25},
    )
    strict_result = run_scoring(evidence, "numerical", params=strict)
    assert strict_result.overall.weighted_score < default_result.overall.weighted_score

    # Custom thresholds must move the grade LABEL through the same pipeline.
    relabeled = dataclasses.replace(
        DEFAULT_PARAMS,
        grade_thresholds=((9.9, "Exemplary"), (9.8, "Good"), (9.7, "Adequate"), (0.1, "Poor")),
    )
    relabeled_result = run_scoring(evidence, "numerical", params=relabeled)
    assert relabeled_result.overall.grade == "Poor"
    assert relabeled_result.principles["p1"].grade == "Poor"
