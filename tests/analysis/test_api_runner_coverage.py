"""Extended tests for _api_runner.py: parse_findings salvage of partial and malformed output."""
from __future__ import annotations

import time

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_schema import parse_findings


# ---------------------------------------------------------------------------
# parse_findings
# ---------------------------------------------------------------------------

class TestSalvagePartialFindings:
    def test_extracts_valid_findings_from_malformed_json(self):
        raw = '{"findings": [{"req":"S-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"test","snippet":"x = 1","reason":"bad"}, BROKEN'
        result, _ = parse_findings(raw)
        assert len(result) >= 1
        assert result[0]["req"] == "S-1"

    def test_returns_empty_for_completely_invalid(self):
        result, _ = parse_findings("totally invalid no json here")
        assert result == []

    def test_skips_invalid_objects(self):
        # First object is well-formed and valid; second lacks required fields and must be dropped.
        raw = (
            '{"req":"X-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"ok","snippet":"x = 1","reason":"r"} '
            '{"not_a_finding": true}'
        )
        result, _ = parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "X-1"

    def test_handles_multiple_valid_objects(self):
        raw = (
            '{"req":"A-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"one","snippet":"x = 1","reason":"r"} '
            '{"req":"B-2","t":"compliance","file":"b.py","line":2,"severity":"major","w":"two","snippet":"y = 2","reason":"r"}'
        )
        result, _ = parse_findings(raw)
        assert len(result) == 2

    def test_handles_finding_with_nested_req_refs(self):
        """The shallow-regex predecessor silently dropped any finding with a
        nested object; this was the exact failure pattern reported in a real
        run where the model emitted ``req_refs: [{"label": "CWE-..."}]``."""
        raw = (
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"nested","snippet":"x = 1","reason":"r",'
            '"req_refs":[{"label":"CWE-79","url":"https://example.com"}]}'
        )
        result, _ = parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "R-MAT-5"

    def test_handles_bare_findings_concatenated(self):
        """Reproduces the production failure where the model emitted two
        bare finding objects back-to-back (no array wrapper, no separator).
        The JSON parser stops at "trailing characters" after the first."""
        raw = (
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":10,'
            '"severity":"minor","w":"first","snippet":"foo","reason":"one"}\n'
            '{"req":"R-FT-1","t":"violation","file":"b.py","line":11,'
            '"severity":"minor","w":"second","snippet":"bar","reason":"two"}'
        )
        result, _ = parse_findings(raw)
        assert len(result) == 2
        assert {r["req"] for r in result} == {"R-MAT-5", "R-FT-1"}

    def test_handles_wrapped_findings_array(self):
        """If the model returned the canonical {"findings":[...]} but
        parsing still needed to walk the structure, the parser should
        recover everything."""
        raw = (
            '{"findings":['
            '{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"one","snippet":"x","reason":"r"},'
            '{"req":"B-2","t":"compliance","file":"b.py","line":2,'
            '"severity":"minor","w":"two","snippet":"y","reason":"r"}'
            ']}'
        )
        result, _ = parse_findings(raw)
        assert len(result) == 2

    def test_handles_findings_buried_in_error_preamble(self):
        """The parser must skip non-JSON preamble text and find the JSON
        object that follows."""
        raw = (
            "1 validation error for _Findings\n"
            "Invalid JSON: trailing characters at line 10 column 4\n"
            "input_value='"
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":3,'
            '"severity":"minor","w":"ok","snippet":"x","reason":"r"}'
            "', input_type=str"
        )
        result, _ = parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "R-MAT-5"

    def test_parse_findings_returns_findings_and_drop_count(self):
        raw = (
            '{"findings":['
            '{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"good","snippet":"x","reason":"valid"},'
            '{"req":"B-2","t":"violation","file":"b.py","line":2,'
            '"severity":"minor","w":"bad","snippet":"y"}'  # missing reason
            ']}'
        )
        findings, dropped = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert dropped == 1

    def test_parse_findings_zero_drops_on_clean_input(self):
        raw = (
            '{"findings":[{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"w","snippet":"x","reason":"r"}]}'
        )
        findings, dropped = parse_findings(raw)
        assert len(findings) == 1
        assert dropped == 0

    def test_parse_findings_container_not_counted_as_drop(self):
        findings, dropped = parse_findings('{"findings":[]}')
        assert findings == []
        assert dropped == 0

    def test_parse_findings_invalid_finding_counted_once_not_recursed(self):
        # A req-bearing dict that fails validation and has a nested req-bearing
        # object must count as exactly ONE drop (we stop, don't recurse in).
        raw = '{"req":"A-1","t":"violation","extras":{"req":"B-2","t":"violation"}}'
        findings, dropped = parse_findings(raw)
        assert findings == []
        assert dropped == 1

    def test_parse_findings_recovers_finding_nested_in_container(self):
        # A container without `req` is recursed, so a valid finding nested
        # inside it is still recovered.
        raw = (
            '{"wrapper":{"findings":[{"req":"A-1","t":"violation","file":"a.py",'
            '"line":1,"severity":"minor","w":"w","snippet":"x","reason":"r"}]}}'
        )
        findings, dropped = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert dropped == 0

    _VALID = (
        '{"req":"A-1","t":"violation","file":"a.py","line":1,'
        '"severity":"minor","w":"w","snippet":"x","reason":"r"}'
    )

    def test_parse_findings_survives_interleaved_stray_openers(self):
        # Local models sometimes wrap output in unbalanced brackets. Every
        # stray opener is a failed decode the walk must step past without
        # losing the real findings behind it.
        raw = "{[" * 500 + self._VALID + " " + "]}" * 500 + self._VALID
        findings, dropped = parse_findings(raw)
        assert [f["req"] for f in findings] == ["A-1", "A-1"]
        assert dropped == 0

    def test_parse_findings_stray_openers_scan_stays_linear(self):
        # Thousands of stray "{" ahead of a long bracket-free tail. Re-scanning
        # the tail for the far "[" after every failed decode made this take
        # seconds; one forward search per hop keeps the walk linear.
        raw = "{" * 16_000 + "x" * 8_000_000 + "[" + self._VALID + "]"
        t0 = time.perf_counter()
        findings, dropped = parse_findings(raw)
        elapsed = time.perf_counter() - t0
        assert [f["req"] for f in findings] == ["A-1"]
        assert dropped == 0
        assert elapsed < 5.0, f"stray-opener walk took {elapsed:.2f}s (budget 5s; the old rescan needed seconds more)"
