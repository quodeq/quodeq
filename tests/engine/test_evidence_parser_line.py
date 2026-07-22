"""Tests for _parse_jsonl_line (JSONL line parsing)."""
from __future__ import annotations

import json

from quodeq.core.evidence.parser import _parse_jsonl_line
from tests.engine.conftest import _evidence_line


class TestParseJsonlLine:
    def test_valid_violation(self):
        result = _parse_jsonl_line(_evidence_line())
        assert result is not None
        j, llm_refs = result
        assert j.practice_id == "ts-001"
        assert j.verdict == "violation"
        assert j.file == "src/app.ts"
        assert j.line == 10
        assert j.severity == "high"
        assert llm_refs is None

    def test_valid_compliance(self):
        result = _parse_jsonl_line(_evidence_line(t="compliance"))
        assert result is not None
        j, _ = result
        assert j.verdict == "compliance"

    def test_missing_practice_id(self):
        line = json.dumps({"t": "violation", "d": "security"})
        assert _parse_jsonl_line(line) is None

    def test_missing_verdict(self):
        line = json.dumps({"p": "ts-001", "d": "security"})
        assert _parse_jsonl_line(line) is None

    def test_invalid_verdict(self):
        assert _parse_jsonl_line(_evidence_line(t="dismissed")) is None

    def test_empty_line(self):
        assert _parse_jsonl_line("") is None
        assert _parse_jsonl_line("   ") is None

    def test_invalid_json(self):
        assert _parse_jsonl_line("not json") is None

    def test_non_object_json_skipped(self):
        """Regression: valid JSON that is not an object (array, string,
        number) must be skipped, not raise AttributeError at obj.get."""
        assert _parse_jsonl_line('["p", "t"]') is None
        assert _parse_jsonl_line('"just a string"') is None
        assert _parse_jsonl_line("42") is None


class TestProvenanceDowngradeRoundTrip:
    """Issue #656: the provenance_downgrade marker must survive the
    JSONL -> Judgment -> PrincipleEvidence-dict round-trip so it reaches the
    report JSON (and from there the dashboard)."""

    def test_parse_reads_provenance_downgrade(self):
        line = json.dumps({
            "p": "R-FT-2", "t": "violation", "d": "security",
            "file": "f.py", "line": 1, "reason": "r", "severity": "major",
            "provenance_downgrade": True,
        })
        result = _parse_jsonl_line(line)
        assert result is not None
        j, _ = result
        assert j.provenance_downgrade is True

    def test_parse_defaults_provenance_downgrade_false(self):
        result = _parse_jsonl_line(_evidence_line())
        assert result is not None
        j, _ = result
        assert j.provenance_downgrade is False

    def test_judgment_to_dict_emits_marker_only_when_true(self):
        from quodeq.core.events.models import Judgment
        from quodeq.core.evidence._jsonl import judgment_to_dict

        downgraded = Judgment(
            practice_id="R-FT-2", verdict="violation", dimension="security",
            file="f.py", line=1, reason="r", severity="major",
            provenance_downgrade=True,
        )
        assert judgment_to_dict(downgraded)["provenance_downgrade"] is True

        normal = Judgment(
            practice_id="P1", verdict="violation", dimension="d",
            file="f.py", line=1, reason="r",
        )
        assert "provenance_downgrade" not in judgment_to_dict(normal)

    def test_defaults(self):
        line = json.dumps({"p": "ts-001", "t": "violation"})
        result = _parse_jsonl_line(line)
        j, _ = result
        assert j.file == ""
        assert j.line == 0
        assert j.severity == "medium"

    def test_req_parsed(self):
        result = _parse_jsonl_line(_evidence_line(req="R-FT-1"))
        assert result is not None
        j, _ = result
        assert j.req == "R-FT-1"

    def test_refs_parsed(self):
        result = _parse_jsonl_line(_evidence_line(refs=["CWE-391", "ERR05-J"]))
        assert result is not None
        j, llm_refs = result
        assert llm_refs == ["CWE-391", "ERR05-J"]

    def test_pre_resolved_req_refs_set_on_judgment(self):
        """req_refs from MCP enrichment are set directly on Judgment."""
        refs = [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}]
        result = _parse_jsonl_line(_evidence_line(req_refs=refs))
        assert result is not None
        j, llm_refs = result
        assert [{"label": r.label, "url": r.url} for r in j.req_refs] == refs
        assert llm_refs is None  # no LLM refs field

    def test_pre_resolved_req_refs_empty_list_ignored(self):
        """Empty req_refs list should not override downstream resolution."""
        result = _parse_jsonl_line(_evidence_line(req_refs=[]))
        assert result is not None
        j, _ = result
        assert j.req_refs == []
