"""Tests for quodeq.provider.violations — resolution and aggregation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.provider.violations import (
    ViolationContext,
    aggregate_violations,
    resolve_dimension_eval,
)


class TestViolationContext:
    def test_frozen_dataclass(self):
        ctx = ViolationContext(project="proj", run_id="run-1", dimension="security")
        assert ctx.project == "proj"
        assert ctx.run_id == "run-1"
        assert ctx.dimension == "security"
        with pytest.raises(AttributeError):
            ctx.project = "other"


class TestAggregateViolations:
    def test_empty_dashboard(self):
        result = aggregate_violations({})
        assert result["total"] == 0
        assert result["critical"] == 0
        assert result["files"] == []

    def test_counts_severities(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 3, "severity": {"critical": 1, "major": 1, "minor": 1}},
                    "violations": [
                        {"file": "a.py", "severity": "critical"},
                        {"file": "a.py", "severity": "major"},
                        {"file": "b.py", "severity": "minor"},
                    ],
                }
            ]
        }
        result = aggregate_violations(dashboard)
        assert result["total"] == 3
        assert result["critical"] == 1
        assert result["major"] == 1
        assert result["minor"] == 1
        assert len(result["files"]) == 2
        top = result["files"][0]
        assert top["path"] == "a.py"
        assert top["count"] == 2

    def test_violations_without_file_skipped(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 1, "severity": {}},
                    "violations": [{"severity": "minor"}],
                }
            ]
        }
        result = aggregate_violations(dashboard)
        assert result["files"] == []


class TestResolveDimensionEval:
    def test_returns_none_when_no_files(self, tmp_path):
        base = tmp_path / "run-1"
        base.mkdir()
        (base / "evaluation").mkdir()
        (base / "evidence").mkdir()
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is None

    def test_resolves_from_evidence_json(self, tmp_path):
        base = tmp_path / "run-1"
        evidence_dir = base / "evidence"
        evidence_dir.mkdir(parents=True)
        eval_dir = base / "evaluation"
        eval_dir.mkdir()
        evidence = {
            "principles": {
                "p1": {
                    "display_name": "Principle 1",
                    "violations": [{"file": "a.py", "line": 10, "reason": "bad"}],
                }
            }
        }
        (evidence_dir / "security_evidence.json").write_text(json.dumps(evidence))
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is not None
        assert result["dimension"] == "security"
        assert len(result["violations"]) == 1

    def test_resolves_from_eval_json(self, tmp_path):
        base = tmp_path / "run-1"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        eval_data = {"dimension": "security", "overallGrade": "B", "principles": {}}
        (eval_dir / "security.json").write_text(json.dumps(eval_data))
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is not None
