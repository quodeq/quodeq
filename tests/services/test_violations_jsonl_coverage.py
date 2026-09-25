"""Tests for quodeq.services._violations_jsonl — JSONL finding parsing."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from quodeq.services._violations_jsonl import _parse_jsonl_findings


# ---------------------------------------------------------------------------
# #145 — non-dict JSON values (lists, strings, numbers) must be skipped
# ---------------------------------------------------------------------------

class TestNonDictJsonlLineIsSkipped:
    def test_non_dict_string_line_is_skipped(self):
        lines = [
            '"just a string"',
            '[1, 2, 3]',
            json.dumps({"p": "M-MOD-1", "t": "violation", "file": "a.py", "line": 1}),
        ]
        violations, _ = _parse_jsonl_findings(lines, "security")
        assert len(violations) == 1

    def test_non_dict_list_line_is_skipped(self):
        lines = ['[{"p": "M-MOD-1", "t": "violation"}]']
        violations, compliance = _parse_jsonl_findings(lines, "security")
        assert violations == []
        assert compliance == []

    def test_non_dict_null_line_is_skipped(self):
        lines = ['null', json.dumps({"p": "P1", "t": "compliance", "file": "b.py", "line": 2})]
        _, compliance = _parse_jsonl_findings(lines, "security")
        assert len(compliance) == 1


class TestParseJsonlFindings:
    def test_empty_lines(self):
        v, c = _parse_jsonl_findings(["", "  ", "\n"], "security")
        assert v == []
        assert c == []

    def test_invalid_json(self):
        v, c = _parse_jsonl_findings(["not json", "{bad"], "security")
        assert v == []
        assert c == []

    def test_missing_principle(self):
        v, c = _parse_jsonl_findings([json.dumps({"t": "violation"})], "sec")
        assert v == []

    def test_invalid_type(self):
        v, c = _parse_jsonl_findings([json.dumps({"p": "P1", "t": "unknown"})], "sec")
        assert v == []

    def test_violations_and_compliance(self):
        lines = [
            json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1}),
            json.dumps({"p": "P2", "t": "compliance", "file": "b.py", "line": 2}),
        ]
        v, c = _parse_jsonl_findings(lines, "security")
        assert len(v) == 1
        assert len(c) == 1

    def test_deduplication(self):
        line = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1})
        v, c = _parse_jsonl_findings([line, line], "security")
        assert len(v) == 1

    def test_dismissed_key_filtering(self):
        from quodeq.services.suppression_keys import SuppressionKeys
        line = json.dumps({"p": "P1", "req": "M-MOD-3", "t": "violation", "file": "a.py", "line": 1})
        keys = SuppressionKeys({("M-MOD-3", "a.py", 1)})
        v, c = _parse_jsonl_findings([line], "security", keys=keys)
        assert len(v) == 0

    def test_req_to_principle_mapping(self):
        from quodeq.core.evidence.req_mapping import PrincipleResolver
        line = json.dumps({"p": "REQ-1", "t": "compliance", "file": "a.py", "line": 1})
        resolver = PrincipleResolver({"REQ-1": "Authentication"}, frozenset({"Authentication"}))
        v, c = _parse_jsonl_findings([line], "security", resolver=resolver)
        assert len(c) == 1
        assert c[0].practice_id == "Authentication"

    def test_unmappable_finding_is_skipped(self):
        """Matches the report path, which quarantines it out of the evaluation."""
        from quodeq.core.evidence.req_mapping import PrincipleResolver
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

        # #10568 — evaluators_dir is injectable (defaults to
        # default_paths().evaluators_dir, resolved at call time) and is
        # authoritative over compiled_dir when it defines the dimension.
        custom_evaluators = tmp_path / "custom-evaluators"
        custom_evaluators.mkdir()
        (custom_evaluators / "security.json").write_text(json.dumps({
            "principles": [
                {"name": "InjectedPrinciple", "requirements": [{"id": "REQ-9"}]},
            ]
        }))
        injected = _build_resolver("security", compiled, evaluators_dir=custom_evaluators)
        assert injected.resolve("REQ-9") == "InjectedPrinciple"

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

        # #10568 — evaluators_dir flows from this public entry point into
        # _build_resolver, instead of always reading default_paths().
        custom_evaluators = tmp_path / "custom-evaluators"
        custom_evaluators.mkdir()
        (custom_evaluators / "sec").with_suffix(".json").write_text(json.dumps({
            "principles": [
                {"name": "InjectedPrinciple", "requirements": [{"id": "REQ-9"}]},
            ]
        }))
        req_jsonl = tmp_path / "req-findings.jsonl"
        req_jsonl.write_text(json.dumps({"req": "REQ-9", "t": "violation", "file": "a.py", "line": 1}) + "\n")
        with patch("quodeq.services._violations_jsonl.build_req_refs_lookup", return_value=None):
            injected = parse_violations_from_jsonl(req_jsonl, None, ctx, evaluators_dir=custom_evaluators)
        assert injected is not None
        assert len(injected.violations) == 1
        assert injected.violations[0].practice_id == "InjectedPrinciple"


# ---------------------------------------------------------------------------
# #1218 — the live view must accept the project's real DismissedKeys
# ---------------------------------------------------------------------------

class TestLiveViewAcceptsDismissedKeys:
    """The live JSONL view is what the evaluation screen reads while a
    dimension is still running, before its report exists.

    Production hands it the project's ``DismissedKeys``; only tests hand it the
    legacy bare ``{(req, file, line)}`` set. Flattening the former with
    ``frozenset()`` yielded a set of ``DismissedEntry`` objects, which is
    neither form, and ``as_dismissed_keys`` raised ``TypeError`` unpacking each
    entry as a 3-tuple. Every project with a dismissal therefore got a 500 from
    this path, and the screen it feeds showed no findings for the whole run.
    """

    def _lines(self):
        return [
            json.dumps({"p": "S-AUT-3", "t": "violation", "file": "a.py", "line": 1}),
            json.dumps({"p": "S-INT-1", "t": "violation", "file": "b.py", "line": 2}),
        ]

    def test_dismissed_keys_object_does_not_raise(self):
        from quodeq.core.dismissals import DismissedKeys
        from quodeq.services.suppression_keys import SuppressionKeys

        keys = SuppressionKeys(DismissedKeys.from_line_keys({("S-AUT-3", "a.py", 1)}), frozenset())
        violations, _ = _parse_jsonl_findings(self._lines(), "security", keys=keys)
        # The dismissed one is filtered, the other survives. Before the fix
        # this raised TypeError instead of returning anything at all.
        assert [v.file for v in violations] == ["b.py"]

    def test_empty_dismissed_keys_object_does_not_raise(self):
        from quodeq.core.dismissals import DismissedKeys
        from quodeq.services.suppression_keys import SuppressionKeys

        keys = SuppressionKeys(DismissedKeys(), frozenset())
        violations, _ = _parse_jsonl_findings(self._lines(), "security", keys=keys)
        assert len(violations) == 2

    def test_legacy_bare_line_key_set_still_works(self):
        from quodeq.services.suppression_keys import SuppressionKeys

        keys = SuppressionKeys(frozenset({("S-AUT-3", "a.py", 1)}), frozenset())
        violations, _ = _parse_jsonl_findings(self._lines(), "security", keys=keys)
        assert [v.file for v in violations] == ["b.py"]
