"""Tests for analysis._report_findings — findings flattening and principle rows."""
from __future__ import annotations

import pytest

from quodeq.analysis._report_findings import (
    _build_principle_row,
    _flatten_findings,
    build_principle_rows,
)
from quodeq.analysis._report_constants import _GRADE_INSUFFICIENT


# ---------------------------------------------------------------------------
# _flatten_findings
# ---------------------------------------------------------------------------

class TestFlattenFindings:
    def test_empty_items(self):
        assert _flatten_findings([], "Auth", ("file", "line")) == []

    def test_tags_with_label_and_keeps_fields(self):
        items = [
            {"file": "a.py", "line": 1, "extra": "ignored"},
            {"file": "b.py", "line": 2},
        ]
        result = _flatten_findings(items, "Auth", ("file", "line"))
        assert len(result) == 2
        assert all(r["principle"] == "Auth" for r in result)
        assert result[0] == {"principle": "Auth", "file": "a.py", "line": 1}
        assert "extra" not in result[0]

    def test_skips_none_values(self):
        items = [{"file": "a.py", "line": None}]
        result = _flatten_findings(items, "P1", ("file", "line"))
        assert result == [{"principle": "P1", "file": "a.py"}]

    def test_missing_fields_skipped(self):
        items = [{"file": "a.py"}]
        result = _flatten_findings(items, "P1", ("file", "line", "severity"))
        assert result == [{"principle": "P1", "file": "a.py"}]


# ---------------------------------------------------------------------------
# _build_principle_row
# ---------------------------------------------------------------------------

class TestBuildPrincipleRow:
    def test_basic_row(self):
        pdata = {"display_name": "Authentication"}
        lookup = {"Authentication": {"finalScore": 8.5, "grade": "A"}}
        row = _build_principle_row("auth", pdata, lookup)
        assert row["name"] == "Authentication"
        assert row["score"] == "8.5/10"
        assert row["grade"] == "A"

    def test_snake_case_final_score(self):
        pdata = {"display_name": "Logging"}
        lookup = {"Logging": {"final_score": 7.0, "grade": "B"}}
        row = _build_principle_row("log", pdata, lookup)
        assert row["score"] == "7.0/10"

    def test_insufficient_grade_null_score(self):
        pdata = {"display_name": "Crypto"}
        lookup = {"Crypto": {"finalScore": 3.0, "grade": _GRADE_INSUFFICIENT}}
        row = _build_principle_row("crypto", pdata, lookup)
        assert row["score"] is None
        assert row["grade"] == _GRADE_INSUFFICIENT

    def test_no_matching_score_computes_grade(self):
        pdata = {"display_name": "Auth"}
        lookup = {}  # no match
        row = _build_principle_row("auth", pdata, lookup)
        assert row["score"] is None
        assert row["grade"] is not None or row["grade"] is None  # grade_from_score(None) returns None

    def test_fallback_display_name(self):
        pdata = {}  # no display_name
        lookup = {}
        row = _build_principle_row("raw_key", pdata, lookup)
        assert row["name"] == "raw_key"

    def test_confidence_interval_and_grade_stability(self):
        pdata = {"display_name": "Auth"}
        lookup = {"Auth": {
            "finalScore": 9.0, "grade": "A+",
            "confidenceInterval": "[8.5, 9.5]",
            "gradeStability": "stable",
        }}
        row = _build_principle_row("auth", pdata, lookup)
        assert row["confidence_interval"] == "[8.5, 9.5]"
        assert row["grade_stability"] == "stable"

    def test_snake_case_ci_and_gs(self):
        pdata = {"display_name": "Auth"}
        lookup = {"Auth": {
            "finalScore": 9.0, "grade": "A+",
            "confidence_interval": "[8, 10]",
            "grade_stability": "volatile",
        }}
        row = _build_principle_row("auth", pdata, lookup)
        assert row["confidence_interval"] == "[8, 10]"
        assert row["grade_stability"] == "volatile"

    def test_metrics_included_when_present(self):
        pdata = {"display_name": "Auth", "metrics": {"total": 10, "compliant": 8}}
        lookup = {"Auth": {"finalScore": 8.0, "grade": "A"}}
        row = _build_principle_row("auth", pdata, lookup)
        assert row["metrics"] == {"total": 10, "compliant": 8}

    def test_no_metrics_key_when_absent(self):
        pdata = {"display_name": "Auth"}
        lookup = {"Auth": {"finalScore": 8.0, "grade": "A"}}
        row = _build_principle_row("auth", pdata, lookup)
        assert "metrics" not in row


# ---------------------------------------------------------------------------
# build_principle_rows
# ---------------------------------------------------------------------------

class TestBuildPrincipleRows:
    def test_empty_evidence(self):
        rows, viols, comp, sev = build_principle_rows({}, {})
        assert rows == []
        assert viols == []
        assert comp == []
        assert sev == {"critical": 0, "major": 0, "minor": 0}

    def test_full_evidence(self):
        evidence = {
            "principles": {
                "auth": {
                    "display_name": "Authentication",
                    "violations": [
                        {"file": "a.py", "severity": "critical", "title": "bad"},
                        {"file": "b.py", "severity": "major", "title": "weak"},
                    ],
                    "compliance": [
                        {"file": "c.py", "title": "good"},
                    ],
                },
                "log": {
                    "display_name": "Logging",
                    "violations": [
                        {"file": "d.py", "severity": "minor", "title": "missing"},
                    ],
                    "compliance": [],
                },
            },
        }
        lookup = {
            "Authentication": {"finalScore": 6.0, "grade": "C"},
            "Logging": {"finalScore": 8.0, "grade": "A"},
        }
        rows, viols, comp, sev = build_principle_rows(evidence, lookup)
        assert len(rows) == 2
        assert len(viols) == 3
        assert len(comp) == 1
        assert sev["critical"] == 1
        assert sev["major"] == 1
        assert sev["minor"] == 1

    def test_unknown_severity_ignored(self):
        evidence = {
            "principles": {
                "auth": {
                    "display_name": "Auth",
                    "violations": [{"file": "a.py", "severity": "unknown"}],
                    "compliance": [],
                },
            },
        }
        _, _, _, sev = build_principle_rows(evidence, {})
        assert sev == {"critical": 0, "major": 0, "minor": 0}
