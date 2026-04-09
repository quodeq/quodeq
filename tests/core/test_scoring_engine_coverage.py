"""Tests for core.scoring.engine — scoring engine orchestration."""
from __future__ import annotations

import pytest

from quodeq.core.scoring.engine import (
    confidence_label,
    grade_for_score,
    run_scoring,
    score_evidence,
)
from quodeq.core.evidence.model import Evidence, PrincipleEvidence


# ---------------------------------------------------------------------------
# grade_for_score
# ---------------------------------------------------------------------------

class TestGradeForScore:
    def test_high_score(self):
        grade = grade_for_score(9.5)
        assert isinstance(grade, str)
        assert grade  # non-empty

    def test_zero_score(self):
        grade = grade_for_score(0.0)
        assert isinstance(grade, str)

    def test_perfect_score(self):
        grade = grade_for_score(10.0)
        assert isinstance(grade, str)

    def test_mid_score(self):
        grade = grade_for_score(5.0)
        assert isinstance(grade, str)


# ---------------------------------------------------------------------------
# confidence_label
# ---------------------------------------------------------------------------

class TestConfidenceLabel:
    def test_known_labels(self):
        assert confidence_label("low") == "Low"
        assert confidence_label("medium") == "Medium"
        assert confidence_label("high") == "High"

    def test_unknown_label_passthrough(self):
        assert confidence_label("custom") == "custom"

    def test_empty_string(self):
        assert confidence_label("") == ""


# ---------------------------------------------------------------------------
# run_scoring
# ---------------------------------------------------------------------------

def _make_evidence_dict(
    n_violations=1, n_compliance=3, source_file_count=100, files_read=50,
):
    violations = [
        {"file": f"v{i}.py", "line": i, "snippet": "x", "reason": "r",
         "severity": "major", "vt": f"vt-{i}"}
        for i in range(n_violations)
    ]
    compliance = [
        {"file": f"c{i}.py", "line": i, "snippet": "y", "reason": "r"}
        for i in range(n_compliance)
    ]
    return {
        "repository": "test-repo",
        "discipline": "python",
        "date": "2026-04-09",
        "source_file_count": source_file_count,
        "files_read": files_read,
        "coverage_pct": 50.0,
        "principles": {
            "p1": {
                "practice_id": "p1",
                "display_name": "Error Handling",
                "dimension": "reliability",
                "severity": "high",
                "violations": violations,
                "compliance": compliance,
                "metrics": {
                    "total_instances": n_violations + n_compliance,
                    "compliant": n_compliance,
                    "violating": n_violations,
                    "compliance_percentage": (n_compliance / max(1, n_violations + n_compliance)) * 100,
                    "confidence_level": "high",
                    "is_balanced": True,
                },
            },
        },
    }


class TestRunScoring:
    def test_numerical_mode(self):
        ev = _make_evidence_dict()
        result = run_scoring(ev, mode="numerical")
        assert result.mode == "numerical"
        assert result.repository == "test-repo"
        assert result.discipline == "python"
        assert result.principles is not None
        assert "p1" in result.principles
        assert result.overall is not None
        assert result.scale is not None

    def test_non_numerical_mode(self):
        ev = _make_evidence_dict()
        result = run_scoring(ev, mode="non-numerical")
        assert result.mode == "non-numerical"
        p1 = result.principles.get("p1")
        assert p1 is not None
        assert p1.grade is not None

    def test_empty_principles(self):
        ev = {
            "repository": "test",
            "discipline": "python",
            "date": "2026-04-09",
            "source_file_count": 0,
            "files_read": 0,
            "principles": {},
        }
        result = run_scoring(ev, mode="numerical")
        assert result.principles == {}
        assert result.overall.weighted_score == 0.0

    def test_scale_info_populated(self):
        ev = _make_evidence_dict(source_file_count=500, files_read=250)
        result = run_scoring(ev, mode="numerical")
        assert result.scale.files_read == 250
        assert result.scale.multiplier is not None
        assert result.scale.tier is not None

    def test_small_project_scale(self):
        ev = _make_evidence_dict(source_file_count=5, files_read=5)
        result = run_scoring(ev, mode="numerical")
        assert result.scale.tier is not None


# ---------------------------------------------------------------------------
# score_evidence
# ---------------------------------------------------------------------------

class TestScoreEvidence:
    def test_from_evidence_object(self):
        pe = PrincipleEvidence(
            practice_id="p1",
            display_name="Error Handling",
            dimension="reliability",
            severity="high",
            violations=[
                {"file": "a.py", "line": 1, "snippet": "x", "reason": "r", "severity": "major", "vt": "vt1"},
            ],
            compliance=[
                {"file": "b.py", "line": 2, "snippet": "y", "reason": "r"},
            ],
            metrics={
                "total_instances": 2,
                "compliant": 1,
                "violating": 1,
                "compliance_percentage": 50.0,
                "confidence_level": "high",
                "is_balanced": True,
            },
        )
        ev = Evidence(
            repository="test",
            language="python",
            date="2026-04-09",
            source_file_count=50,
            files_read=25,
            coverage_pct=50.0,
            principles={"p1": pe},
        )
        result = score_evidence(ev, mode="numerical")
        assert result.mode == "numerical"
        assert "p1" in result.principles

    def test_default_mode_is_numerical(self):
        ev = Evidence(
            repository="test",
            language="python",
            date="2026-04-09",
            source_file_count=0,
            files_read=0,
            coverage_pct=0.0,
        )
        result = score_evidence(ev)
        assert result.mode == "numerical"
