"""Extended tests for dismissed findings — restore_all, recount_totals, filter_dismissed."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.services.dismissed import (
    dismiss_finding,
    filter_dismissed_from_dimensions,
    load_dismissed,
    recount_totals,
    restore_all_findings,
    restore_finding,
)


class TestRestoreAllFindings:
    def test_restore_all_returns_count(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        dismiss_finding(project_dir, {"req": "B", "file": "b.py", "line": 2})
        count = restore_all_findings(project_dir)
        assert count == 2
        assert not (project_dir / "dismissed.json").exists()

    def test_restore_all_empty_returns_zero(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        assert restore_all_findings(project_dir) == 0

    def test_restore_single_deletes_file_when_empty(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        restore_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        assert not (project_dir / "dismissed.json").exists()


class TestLoadDismissedEdgeCases:
    def test_load_corrupt_json(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dismissed.json").write_text("not json")
        result = load_dismissed(project_dir)
        assert result == []


class TestRecountTotals:
    def test_empty_list(self):
        totals = recount_totals([])
        assert totals.violation_count == 0
        assert totals.compliance_count == 0
        assert totals.severity.critical == 0

    def test_counts_severities(self):
        violations = [
            Finding(severity="critical"),
            Finding(severity="major"),
            Finding(severity="major"),
            Finding(severity="minor"),
            Finding(severity="unknown"),
        ]
        totals = recount_totals(violations, compliance_count=3)
        assert totals.violation_count == 5
        assert totals.compliance_count == 3
        assert totals.severity.critical == 1
        assert totals.severity.major == 2
        assert totals.severity.minor == 1
        assert totals.severity.unknown == 1

    def test_uses_old_totals_compliance(self):
        old = Totals(violation_count=10, compliance_count=7)
        totals = recount_totals([], old_totals=old)
        assert totals.compliance_count == 7

    def test_compliance_count_overrides_old(self):
        old = Totals(compliance_count=7)
        totals = recount_totals([], compliance_count=5, old_totals=old)
        assert totals.compliance_count == 5


@dataclass
class _FakeDimension:
    """Simulates DimensionResult for testing filter_dismissed_from_dimensions."""
    violations: list[Finding] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)


class TestFilterDismissedFromDimensions:
    def test_no_dismissed_returns_same(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dim = _FakeDimension(violations=[Finding(req="A", file="a.py", line=1)])
        result = filter_dismissed_from_dimensions([dim], project_dir)
        assert len(result) == 1
        assert len(result[0].violations) == 1

    def test_filters_dismissed_findings(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        dim = _FakeDimension(
            violations=[
                Finding(req="A", file="a.py", line=1, severity="minor"),
                Finding(req="B", file="b.py", line=2, severity="major"),
            ],
            totals=Totals(violation_count=2, compliance_count=5),
        )
        result = filter_dismissed_from_dimensions([dim], project_dir)
        assert len(result[0].violations) == 1
        assert result[0].violations[0].req == "B"
        assert result[0].totals.violation_count == 1
