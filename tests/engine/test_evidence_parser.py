"""Tests for evidence parser (JSONL -> Evidence model)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.evidence_parser import (
    EvidenceContext,
    parse_jsonl_to_evidence,
    _parse_jsonl_line,
)


def _evidence_line(**overrides) -> str:
    obj = {
        "p": "ts-001",
        "t": "violation",
        "d": "security",
        "w": "eval usage",
        "file": "src/app.ts",
        "line": 10,
        "snippet": "eval(userInput)",
        "severity": "high",
        "vt": "code-injection",
        "reason": "eval is dangerous",
    }
    obj.update(overrides)
    return json.dumps(obj)



# ---------------------------------------------------------------------------
# _parse_jsonl_line
# ---------------------------------------------------------------------------

class TestParseJsonlLine:
    def test_valid_violation(self):
        j = _parse_jsonl_line(_evidence_line())
        assert j is not None
        assert j.practice_id == "ts-001"
        assert j.verdict == "violation"
        assert j.file == "src/app.ts"
        assert j.line == 10
        assert j.severity == "high"

    def test_valid_compliance(self):
        j = _parse_jsonl_line(_evidence_line(t="compliance"))
        assert j is not None
        assert j.verdict == "compliance"

    def test_missing_practice_id(self):
        line = json.dumps({"t": "violation", "d": "security"})
        assert _parse_jsonl_line(line) is None

    def test_missing_verdict(self):
        line = json.dumps({"p": "ts-001", "d": "security"})
        assert _parse_jsonl_line(line) is None

    def test_invalid_verdict(self):
        j = _parse_jsonl_line(_evidence_line(t="dismissed"))
        assert j is None

    def test_empty_line(self):
        assert _parse_jsonl_line("") is None
        assert _parse_jsonl_line("   ") is None

    def test_invalid_json(self):
        assert _parse_jsonl_line("not json") is None

    def test_defaults(self):
        line = json.dumps({"p": "ts-001", "t": "violation"})
        j = _parse_jsonl_line(line)
        assert j.file == ""
        assert j.line == 0
        assert j.severity == "medium"

    def test_req_parsed(self):
        j = _parse_jsonl_line(_evidence_line(req="R-FT-1"))
        assert j is not None
        assert j.req == "R-FT-1"


# ---------------------------------------------------------------------------
# parse_jsonl_to_evidence
# ---------------------------------------------------------------------------

class TestParseJsonlToEvidence:
    def test_basic_parsing(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("\n".join([
            _evidence_line(p="ts-001", t="violation"),
            _evidence_line(p="ts-001", t="compliance", file="src/safe.ts"),
            _evidence_line(p="ts-002", t="violation", d="maintainability"),
        ]) + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test-repo",
                date_str="2026-03-06",
                source_file_count=50,
                files_read=10,
            ),
        )

        assert ev.repository == "test-repo"
        assert ev.plugin_id == "typescript"
        assert ev.source_file_count == 50
        assert ev.files_read == 10
        assert ev.coverage_pct == 20.0
        assert "ts-001" in ev.principles
        assert "ts-002" in ev.principles

    def test_principle_evidence_structure(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("\n".join([
            _evidence_line(p="ts-001", t="violation"),
            _evidence_line(p="ts-001", t="violation", file="src/b.ts", line=20),
            _evidence_line(p="ts-001", t="compliance", file="src/safe.ts"),
        ]) + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=5,
            ),
        )

        pe = ev.principles["ts-001"]
        assert pe.display_name == "ts-001"
        assert pe.dimension == "security"
        assert pe.severity == "high"
        assert len(pe.violations) == 2
        assert len(pe.compliance) == 1
        assert pe.metrics["is_balanced"] is True
        assert pe.metrics["total_instances"] == 3

    def test_empty_jsonl(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=0,
            ),
        )

        assert len(ev.principles) == 0
        assert ev.coverage_pct == 0.0

    def test_missing_jsonl_file(self, tmp_path):
        jsonl = tmp_path / "nonexistent.jsonl"

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=0,
            ),
        )

        assert len(ev.principles) == 0

    def test_unknown_practice_id(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text(_evidence_line(p="unknown-001") + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=5,
            ),
        )

        assert "unknown-001" in ev.principles
        assert ev.principles["unknown-001"].display_name == "unknown-001"

    def test_judgment_dict_fields(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text(_evidence_line() + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=5,
            ),
        )

        v = ev.principles["ts-001"].violations[0]
        assert v["file"] == "src/app.ts"
        assert v["line"] == 10
        assert v["snippet"] == "eval(userInput)"
        assert v["severity"] == "high"
        assert v["reason"] == "eval is dangerous"

    def test_req_field_stored_in_violation(self, tmp_path):
        """req field from JSONL is stored in violation dict."""
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text(json.dumps({
            "p": "Fault Tolerance", "t": "violation", "d": "reliability",
            "w": "empty catch block", "file": "src/app.py", "line": 5,
            "severity": "high", "reason": "exception swallowed", "req": "R-FT-1",
        }) + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="python", repository="test", date_str="2026-03-11",
                source_file_count=10, files_read=5,
            ),
        )

        v = ev.principles["Fault Tolerance"].violations[0]
        assert v["req"] == "R-FT-1"
        assert v["title"] == "empty catch block"
        assert v["reason"] == "exception swallowed"

    def test_no_req_field_still_works(self, tmp_path):
        """Findings without req field are still parsed."""
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text(_evidence_line() + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript", repository="test", date_str="2026-03-11",
                source_file_count=10, files_read=5,
            ),
        )
        assert len(ev.principles) == 1

    def test_malformed_lines_skipped(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("not json\n" + _evidence_line() + "\n{}\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=5,
            ),
        )

        assert len(ev.principles) == 1

    def test_coverage_zero_source_files(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=0,
                files_read=0,
            ),
        )

        assert ev.coverage_pct == 0.0

    def test_v1_evidence_dict_shape(self, tmp_path):
        """Ensure the Evidence object can convert to V1 shape."""
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text("\n".join([
            _evidence_line(p="ts-001", t="violation"),
            _evidence_line(p="ts-001", t="compliance", file="safe.ts"),
        ]) + "\n")

        ev = parse_jsonl_to_evidence(
            jsonl,
            EvidenceContext(
                plugin_id="typescript",
                repository="test",
                date_str="2026-03-06",
                source_file_count=10,
                files_read=5,
            ),
        )

        d = ev.to_evidence_dict()
        assert d["repository"] == "test"
        assert d["discipline"] == "typescript"
        assert "ts-001" in d["principles"]
        assert "violations" in d["principles"]["ts-001"]
        assert "compliance" in d["principles"]["ts-001"]
        assert "metrics" in d["principles"]["ts-001"]
