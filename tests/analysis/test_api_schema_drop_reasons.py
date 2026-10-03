"""The drop count must be able to say WHICH constraint rejected a finding.

Before this, `parse_findings` reported only how many finding-shaped dicts
failed validation. A run showing 102 drops gave no way to tell a systemic
output-shape problem from scattered model slips without replaying prompts
against the model by hand.
"""
from __future__ import annotations

import json

from quodeq.analysis._api_schema import parse_findings
from quodeq.analysis._drop_stats import format_reasons

_VALID = {
    "req": "A-1", "t": "violation", "file": "a.py", "line": 1,
    "severity": "minor", "w": "w", "snippet": "x", "reason": "r",
}


def _raw(*findings: dict) -> str:
    return json.dumps({"findings": list(findings)})


class TestDropReasons:
    def test_names_the_failing_field_and_error_type(self):
        reasons: dict[str, int] = {}
        findings, dropped = parse_findings(
            _raw({**_VALID, "line": 0}), drop_reasons=reasons,
        )

        assert (len(findings), dropped) == (0, 1)
        assert reasons == {"line:greater_than": 1}

    def test_tallies_repeats_of_the_same_constraint(self):
        reasons: dict[str, int] = {}
        parse_findings(
            _raw({**_VALID, "snippet": ""}, {**_VALID, "snippet": ""}),
            drop_reasons=reasons,
        )

        assert reasons == {"snippet:string_too_short": 2}

    def test_distinct_constraints_stay_separate(self):
        reasons: dict[str, int] = {}
        parse_findings(
            _raw({**_VALID, "line": 0}, {**_VALID, "reason": ""}),
            drop_reasons=reasons,
        )

        assert reasons == {"line:greater_than": 1, "reason:string_too_short": 1}

    def test_a_finding_failing_two_constraints_records_both(self):
        reasons: dict[str, int] = {}
        parse_findings(
            _raw({**_VALID, "line": 0, "snippet": ""}), drop_reasons=reasons,
        )

        assert reasons == {"line:greater_than": 1, "snippet:string_too_short": 1}

    def test_clean_input_records_nothing(self):
        reasons: dict[str, int] = {}
        parse_findings(_raw(_VALID), drop_reasons=reasons)

        assert reasons == {}

    def test_collection_is_opt_in(self):
        """Omitting the out-param keeps the original two-value contract."""
        findings, dropped = parse_findings(_raw({**_VALID, "line": 0}))

        assert (findings, dropped) == ([], 1)


class TestFormatReasons:
    def test_ranks_commonest_first(self):
        assert format_reasons({"a:x": 1, "b:y": 9}) == "b:y x9, a:x x1"

    def test_ties_break_on_key_for_a_stable_line(self):
        assert format_reasons({"b:y": 2, "a:x": 2}) == "a:x x2, b:y x2"

    def test_truncates_to_the_limit(self):
        histogram = {f"f{i}:t": 10 - i for i in range(8)}

        assert format_reasons(histogram, limit=2) == "f0:t x10, f1:t x9"

    def test_empty_histogram_reads_as_a_sentence(self):
        assert format_reasons({}) == "reason not recorded"


_DEPTH = 200_000


class TestPathologicalNesting:
    def test_a_deeply_nested_response_yields_no_findings(self):
        deep = "[" * _DEPTH + "]" * _DEPTH
        assert parse_findings(deep) == ([], 0)

    def test_findings_before_the_nesting_are_kept(self):
        deep = "[" * _DEPTH + "]" * _DEPTH
        findings, dropped = parse_findings(_raw(_VALID) + deep)
        assert (len(findings), dropped) == (1, 0)
