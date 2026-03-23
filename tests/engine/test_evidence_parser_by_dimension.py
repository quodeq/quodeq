"""Tests for parse_jsonl_to_evidence_by_dimension."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.evidence.parser import (
    EvidenceContext,
    parse_jsonl_to_evidence_by_dimension,
)


def _write_mixed_jsonl(path: Path):
    """Write a JSONL file with findings from 2 dimensions."""
    findings = [
        {"schema_version": 1, "p": "Confidentiality", "d": "security", "t": "violation",
         "req": "S-CON-1", "file": "a.py", "line": 1, "w": "hardcoded secret",
         "severity": "critical", "snippet": "SECRET='abc'"},
        {"schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
         "req": "M-MOD-1", "file": "b.py", "line": 10, "w": "high complexity",
         "severity": "major", "snippet": "def big():..."},
        {"schema_version": 1, "p": "Confidentiality", "d": "security", "t": "compliance",
         "req": "S-CON-2", "file": "c.py", "line": 5, "w": "no secrets logged",
         "severity": "major", "snippet": "logger.info('ok')"},
    ]
    with open(path, "w") as f:
        for finding in findings:
            f.write(json.dumps(finding) + "\n")


class TestParseJsonlByDimension:
    def test_splits_by_dimension(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_mixed_jsonl(jsonl)
        ctx = EvidenceContext(
            language="python", repository="test", date_str="2026-03-22",
            source_file_count=10, files_read=3,
        )
        result = parse_jsonl_to_evidence_by_dimension(jsonl, ctx)
        assert "security" in result
        assert "maintainability" in result
        # Security has 1 violation + 1 compliance
        sec_violations = sum(len(pe.violations) for pe in result["security"].principles.values())
        sec_compliance = sum(len(pe.compliance) for pe in result["security"].principles.values())
        assert sec_violations == 1
        assert sec_compliance == 1
        # Maintainability has 1 violation
        maint_violations = sum(len(pe.violations) for pe in result["maintainability"].principles.values())
        assert maint_violations == 1

    def test_empty_jsonl(self, tmp_path):
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("")
        ctx = EvidenceContext(
            language="python", repository="test", date_str="2026-03-22",
            source_file_count=0, files_read=0,
        )
        result = parse_jsonl_to_evidence_by_dimension(jsonl, ctx)
        assert result == {}

    def test_single_dimension_produces_one_entry(self, tmp_path):
        jsonl = tmp_path / "single.jsonl"
        with open(jsonl, "w") as f:
            f.write(json.dumps({
                "schema_version": 1, "p": "Modularity", "d": "maintainability",
                "t": "violation", "req": "M-MOD-1", "file": "a.py", "line": 1,
                "w": "test", "severity": "minor", "snippet": "x",
            }) + "\n")
        ctx = EvidenceContext(
            language="python", repository="test", date_str="2026-03-22",
            source_file_count=5, files_read=1,
        )
        result = parse_jsonl_to_evidence_by_dimension(jsonl, ctx)
        assert len(result) == 1
        assert "maintainability" in result
