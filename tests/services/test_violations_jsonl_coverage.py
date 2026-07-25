"""Tests for quodeq.services._violations_jsonl — JSONL finding parsing."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# #145 — non-dict JSON values (lists, strings, numbers) must be skipped
# ---------------------------------------------------------------------------

class TestNonDictJsonlLineIsSkipped:
    def test_non_dict_string_line_is_skipped(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        lines = [
            '"just a string"',
            '[1, 2, 3]',
            json.dumps({"p": "M-MOD-1", "t": "violation", "file": "a.py", "line": 1}),
        ]
        violations, _ = _parse_jsonl_findings(lines, "security")
        assert len(violations) == 1

    def test_non_dict_list_line_is_skipped(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        lines = ['[{"p": "M-MOD-1", "t": "violation"}]']
        violations, compliance = _parse_jsonl_findings(lines, "security")
        assert violations == []
        assert compliance == []

    def test_non_dict_null_line_is_skipped(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        lines = ['null', json.dumps({"p": "P1", "t": "compliance", "file": "b.py", "line": 2})]
        _, compliance = _parse_jsonl_findings(lines, "security")
        assert len(compliance) == 1


class TestParseJsonlFindings:
    def test_empty_lines(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        v, c = _parse_jsonl_findings(["", "  ", "\n"], "security")
        assert v == []
        assert c == []

    def test_invalid_json(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        v, c = _parse_jsonl_findings(["not json", "{bad"], "security")
        assert v == []
        assert c == []

    def test_missing_principle(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        v, c = _parse_jsonl_findings([json.dumps({"t": "violation"})], "sec")
        assert v == []

    def test_invalid_type(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        v, c = _parse_jsonl_findings([json.dumps({"p": "P1", "t": "unknown"})], "sec")
        assert v == []

    def test_violations_and_compliance(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        lines = [
            json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1}),
            json.dumps({"p": "P2", "t": "compliance", "file": "b.py", "line": 2}),
        ]
        v, c = _parse_jsonl_findings(lines, "security")
        assert len(v) == 1
        assert len(c) == 1

    def test_deduplication(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        line = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1})
        v, c = _parse_jsonl_findings([line, line], "security")
        assert len(v) == 1

    def test_dismissed_key_filtering(self):
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        line = json.dumps({"p": "P1", "req": "M-MOD-3", "t": "violation", "file": "a.py", "line": 1})
        dismissed = {("M-MOD-3", "a.py", 1)}
        v, c = _parse_jsonl_findings([line], "security", dismissed_keys=dismissed)
        assert len(v) == 0

    def test_req_to_principle_mapping(self):
        from quodeq.core.evidence._req_mapping import PrincipleResolver
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        line = json.dumps({"p": "REQ-1", "t": "compliance", "file": "a.py", "line": 1})
        resolver = PrincipleResolver({"REQ-1": "Authentication"}, frozenset({"Authentication"}))
        v, c = _parse_jsonl_findings([line], "security", resolver=resolver)
        assert len(c) == 1
        assert c[0].practice_id == "Authentication"

    def test_unmappable_finding_is_skipped(self):
        """Matches the report path, which quarantines it out of the evaluation."""
        from quodeq.core.evidence._req_mapping import PrincipleResolver
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        line = json.dumps({"req": "N/A", "t": "violation", "file": "a.py", "line": 1})
        resolver = PrincipleResolver({"REQ-1": "Authentication"}, frozenset({"Authentication"}))
        v, c = _parse_jsonl_findings([line], "security", resolver=resolver)
        assert v == []


class TestBuildResolver:
    """The live view resolves principles through the shared builder.

    It used to read the evaluators dir itself, with no fallback to the compiled
    built-in standards. On a stock install that dir exists but is empty for
    built-in dimensions, so the map came back empty and requirement IDs never
    resolved to their principle. Malformed-evaluator degradation is covered by
    tests/core/test_req_mapping_robustness.py, which the shared builder shares.
    """

    def test_falls_back_to_compiled_standard(self, tmp_path):
        from quodeq.services._violations_jsonl import _build_resolver
        compiled = tmp_path / "compiled"
        compiled.mkdir()
        (compiled / "security.json").write_text(json.dumps({
            "principles": [
                {"name": "Authentication", "requirements": [{"id": "REQ-1"}]},
            ]
        }))
        resolver = _build_resolver("security", compiled)
        assert resolver.resolve("REQ-1") == "Authentication"
        assert resolver.resolve("Authentication") == "Authentication"
        assert resolver.resolve("N/A") is None

    def test_no_standard_stays_permissive(self, tmp_path):
        from quodeq.services._violations_jsonl import _build_resolver
        resolver = _build_resolver("security", tmp_path / "nonexistent")
        assert resolver.resolve("anything") == "anything"

    def test_rejects_a_traversing_dimension(self, tmp_path):
        """The dimension reaches a path join, so the guard must survive."""
        from quodeq.services._violations_jsonl import _build_resolver
        with pytest.raises(ValueError):
            _build_resolver("../../etc/passwd", tmp_path)


class TestParseViolationsFromJsonl:
    def test_missing_file(self, tmp_path):
        from quodeq.services._violations_jsonl import parse_violations_from_jsonl
        from quodeq.services.violation_context import ViolationContext
        ctx = ViolationContext(dimension="sec", run_id="r1", project="p1")
        result = parse_violations_from_jsonl(
            tmp_path / "missing.jsonl", None, ctx
        )
        assert result is None

    def test_valid_file(self, tmp_path):
        from quodeq.services._violations_jsonl import parse_violations_from_jsonl
        from quodeq.services.violation_context import ViolationContext
        jsonl = tmp_path / "findings.jsonl"
        jsonl.write_text(json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1}) + "\n")
        ctx = ViolationContext(dimension="sec", run_id="r1", project="p1")
        with patch("quodeq.services._violations_jsonl.build_req_refs_lookup", return_value=None):
            result = parse_violations_from_jsonl(jsonl, None, ctx)
            assert result is not None
            assert result.dimension == "sec"
            assert len(result.violations) == 1
