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
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        line = json.dumps({"p": "REQ-1", "t": "compliance", "file": "a.py", "line": 1})
        mapping = {"REQ-1": "Authentication"}
        v, c = _parse_jsonl_findings([line], "security", req_to_principle=mapping)
        assert len(c) == 1


class TestLoadReqToPrinciple:
    def test_no_evaluators_dir(self, tmp_path):
        from quodeq.services._violations_jsonl import _load_req_to_principle
        result = _load_req_to_principle("security", tmp_path / "nonexistent")
        assert result == {}

    def test_no_dimension_file(self, tmp_path):
        from quodeq.services._violations_jsonl import _load_req_to_principle
        tmp_path.mkdir(exist_ok=True)
        result = _load_req_to_principle("security", tmp_path)
        assert result == {}

    def test_valid_dimension_file(self, tmp_path):
        from quodeq.services._violations_jsonl import _load_req_to_principle
        data = {
            "principles": [
                {
                    "name": "Authentication",
                    "requirements": [
                        {"id": "REQ-1"},
                        {"id": "REQ-2"},
                    ]
                }
            ]
        }
        dim_file = tmp_path / "security.json"
        dim_file.write_text(json.dumps(data))
        result = _load_req_to_principle("security", tmp_path)
        assert result == {"REQ-1": "Authentication", "REQ-2": "Authentication"}

    def test_corrupt_json(self, tmp_path):
        from quodeq.services._violations_jsonl import _load_req_to_principle
        (tmp_path / "security.json").write_text("not json")
        result = _load_req_to_principle("security", tmp_path)
        assert result == {}

    @pytest.mark.parametrize("payload", ['[{"name": "x"}]', "null", '"hello"', "42"])
    def test_non_dict_top_level_returns_empty(self, tmp_path, payload):
        """A valid-JSON-but-non-dict evaluator file must not crash with
        AttributeError on data.get(); it degrades to an empty mapping."""
        from quodeq.services._violations_jsonl import _load_req_to_principle
        (tmp_path / "security.json").write_text(payload)
        assert _load_req_to_principle("security", tmp_path) == {}


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
        with patch("quodeq.services._violations_jsonl._load_req_to_principle", return_value={}), \
             patch("quodeq.services._violations_jsonl.build_req_refs_lookup", return_value=None):
            result = parse_violations_from_jsonl(jsonl, None, ctx)
            assert result is not None
            assert result.dimension == "sec"
            assert len(result.violations) == 1
