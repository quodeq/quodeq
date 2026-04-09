"""Tests for _report_assembly.py — report building from evidence and scores."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._report_assembly import (
    _ReportData,
    _assemble_report_dict,
    build_report_json,
    build_full_report,
    build_dashboard_report,
)
from quodeq.analysis._report_constants import _REPORT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# _assemble_report_dict
# ---------------------------------------------------------------------------

class TestAssembleReportDict:
    def test_basic_assembly(self):
        data = _ReportData(
            dimension="security",
            evidence={
                "repository": "test-repo",
                "discipline": "python",
                "date": "2026-04-09",
                "source_file_count": 50,
                "files_read": 25,
                "coverage_pct": 50.0,
                "meta": {
                    "analysis_prompt_version": "v1",
                    "scoring_prompt_version": "v2",
                    "mapping_file_hash": "abc123",
                    "quodeq_version": "1.0.0",
                },
            },
            top_score="8.5/10",
            top_grade="A",
            principle_rows=[{"name": "Auth", "score": "9/10", "grade": "A+"}],
            flat_violations=[{"file": "a.py", "severity": "major"}],
            flat_compliance=[{"file": "b.py"}],
            sev_tally={"critical": 0, "major": 1, "minor": 0},
        )
        report = _assemble_report_dict(data)
        assert report["schema_version"] == _REPORT_SCHEMA_VERSION
        assert report["dimension"] == "security"
        assert report["project"] == "test-repo"
        assert report["discipline"] == "python"
        assert report["date"] == "2026-04-09"
        assert report["sourceFileCount"] == 50
        assert report["filesRead"] == 25
        assert report["coveragePct"] == 50.0
        assert report["overallScore"] == "8.5/10"
        assert report["overallGrade"] == "A"
        assert len(report["principles"]) == 1
        assert len(report["violations"]) == 1
        assert len(report["compliance"]) == 1
        assert report["totals"]["violationCount"] == 1
        assert report["totals"]["complianceCount"] == 1
        assert report["totals"]["severity"] == {"critical": 0, "major": 1, "minor": 0}

    def test_includes_module_when_present(self):
        data = _ReportData(
            dimension="security",
            evidence={"module": "auth-service", "meta": {}},
            top_score=None,
            top_grade=None,
            principle_rows=[],
            flat_violations=[],
            flat_compliance=[],
            sev_tally={},
        )
        report = _assemble_report_dict(data)
        assert report["module"] == "auth-service"

    def test_no_module_key_when_absent(self):
        data = _ReportData(
            dimension="security",
            evidence={"meta": {}},
            top_score=None,
            top_grade=None,
            principle_rows=[],
            flat_violations=[],
            flat_compliance=[],
            sev_tally={},
        )
        report = _assemble_report_dict(data)
        assert "module" not in report

    def test_handles_empty_meta(self):
        data = _ReportData(
            dimension="reliability",
            evidence={"meta": {}},
            top_score=None,
            top_grade=None,
            principle_rows=[],
            flat_violations=[],
            flat_compliance=[],
            sev_tally={},
        )
        report = _assemble_report_dict(data)
        assert report["meta"]["analysis_prompt_version"] is None
        assert report["meta"]["scoring_prompt_version"] is None

    def test_null_scores(self):
        data = _ReportData(
            dimension="security",
            evidence={"meta": {}},
            top_score=None,
            top_grade=None,
            principle_rows=[],
            flat_violations=[],
            flat_compliance=[],
            sev_tally={},
        )
        report = _assemble_report_dict(data)
        assert report["overallScore"] is None
        assert report["overallGrade"] is None


# ---------------------------------------------------------------------------
# build_report_json
# ---------------------------------------------------------------------------

class TestBuildReportJson:
    def test_with_weighted_score(self):
        evidence = {
            "repository": "test",
            "discipline": "python",
            "date": "2026-04-09",
            "source_file_count": 10,
            "files_read": 5,
            "coverage_pct": 50.0,
            "meta": {},
            "principles": {},
        }
        scores = {
            "principles": {},
            "overall": {"weightedScore": 7.5, "grade": "B+"},
        }
        report = build_report_json("security", evidence, scores)
        assert report["overallScore"] == "7.5/10"
        assert report["overallGrade"] == "B+"

    def test_with_snake_case_weighted_score(self):
        evidence = {
            "repository": "test",
            "discipline": "python",
            "date": "2026-04-09",
            "meta": {},
            "principles": {},
        }
        scores = {
            "principles": {},
            "overall": {"weighted_score": 6.3},
        }
        report = build_report_json("reliability", evidence, scores)
        assert report["overallScore"] == "6.3/10"
        assert report["overallGrade"] is not None  # Should compute grade

    def test_no_scores(self):
        evidence = {
            "repository": "test",
            "meta": {},
            "principles": {},
        }
        report = build_report_json("security", evidence, None)
        assert report["overallScore"] is None
        assert report["overallGrade"] is None

    def test_with_principles(self):
        evidence = {
            "repository": "test",
            "meta": {},
            "principles": {
                "auth": {
                    "display_name": "Authentication",
                    "violations": [
                        {"file": "a.py", "line": 1, "title": "weak auth", "severity": "major", "reason": "bad"},
                    ],
                    "compliance": [
                        {"file": "b.py", "line": 2, "title": "good auth", "reason": "ok"},
                    ],
                },
            },
        }
        scores = {
            "principles": {
                "auth": {
                    "displayName": "Authentication",
                    "finalScore": 7.0,
                    "grade": "B",
                },
            },
            "overall": {"weightedScore": 7.0},
        }
        report = build_report_json("security", evidence, scores)
        assert len(report["principles"]) == 1
        assert report["principles"][0]["name"] == "Authentication"
        assert report["principles"][0]["score"] == "7.0/10"
        assert report["principles"][0]["grade"] == "B"
        assert len(report["violations"]) == 1
        assert len(report["compliance"]) == 1
        assert report["totals"]["severity"]["major"] == 1

    def test_grade_computed_from_score_when_missing(self):
        evidence = {
            "repository": "test",
            "meta": {},
            "principles": {},
        }
        scores = {
            "principles": {},
            "overall": {"weightedScore": 9.5},
        }
        report = build_report_json("security", evidence, scores)
        assert report["overallScore"] == "9.5/10"
        assert report["overallGrade"] is not None  # Should compute from score


# ---------------------------------------------------------------------------
# build_full_report
# ---------------------------------------------------------------------------

class TestBuildFullReport:
    def test_includes_dismissed_count_and_summary(self):
        mock_evidence = MagicMock()
        mock_evidence.language = "python"
        mock_evidence.dismissed_count = 5
        mock_evidence.summary.return_value = {"total": 10, "violations": 3}
        mock_evidence.to_evidence_dict.return_value = {
            "repository": "test",
            "discipline": "python",
            "date": "2026-04-09",
            "meta": {},
            "principles": {},
        }

        scores = {"principles": {}, "overall": {"weightedScore": 8.0}}
        report = build_full_report(mock_evidence, scores)
        assert report["dismissed_count"] == 5
        assert report["evidence_summary"] == {"total": 10, "violations": 3}


# ---------------------------------------------------------------------------
# build_dashboard_report
# ---------------------------------------------------------------------------

class TestBuildDashboardReport:
    def test_returns_report_dict(self):
        mock_evidence = MagicMock()
        mock_evidence.language = "typescript"
        mock_evidence.to_evidence_dict.return_value = {
            "repository": "my-app",
            "discipline": "typescript",
            "date": "2026-04-09",
            "meta": {},
            "principles": {},
        }

        scores = {"principles": {}, "overall": {"weightedScore": 7.0}}
        report = build_dashboard_report(mock_evidence, scores)
        assert report["dimension"] == "typescript"
        assert report["project"] == "my-app"
        # Should NOT have dismissed_count (that's only in build_full_report)
        assert "dismissed_count" not in report
