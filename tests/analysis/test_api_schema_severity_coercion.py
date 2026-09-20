"""Regression guard: a grounded finding must survive an unreadable `severity`.

Local models (gemma4-class) mirror the finding *type* into the severity slot on
compliance findings -- `"t": "compliance"` alongside `"severity": "compliance"`
-- because the prompt marked severity required while offering only
violation-shaped values. The enum rejected that, and `_extract_finding_dicts`
discarded the whole finding: snippet, line, reason and all.

Severity is not one of the grounding fields #305 tightened (`snippet`, `reason`,
`line`). It is optional with a default, so an unreadable value carries no less
information than an absent one and must not cost a grounded finding.
"""
from __future__ import annotations

import json

import pytest

from quodeq.analysis._api_schema import _Finding, _parse_findings

# The exact shape gemma4:26b-mlx emitted, captured from a live run.
_COMPLIANCE_FINDING = {
    "req": "S-AUT-3",
    "t": "compliance",
    "file": "src/quodeq/services/fs_projects.py",
    "line": 165,
    "severity": "compliance",
    "w": "Path traversal protection via scope validation",
    "reason": "The code uses `is_within` to ensure the resolved project_dir "
              "remains within the reports_root boundary.",
    "snippet": "    if not is_within(project_dir, reports_root):",
    "end_line": 166,
    "vt": "path-traversal",
}


class TestSeverityCoercion:
    def test_type_mirrored_into_severity_keeps_the_finding(self):
        finding = _Finding.model_validate(_COMPLIANCE_FINDING)

        assert finding.severity.value == "minor"
        assert finding.t.value == "compliance"
        # The grounding fields survive untouched -- that is the point.
        assert finding.line == 165
        assert finding.snippet == "    if not is_within(project_dir, reports_root):"

    @pytest.mark.parametrize("raw", ["violation", "compliance", "high", "", "  ", None, 3])
    def test_unreadable_severity_falls_back_to_the_default(self, raw):
        finding = _Finding.model_validate({**_COMPLIANCE_FINDING, "severity": raw})

        assert finding.severity.value == "minor"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("Major", "major"), ("CRITICAL", "critical"), ("  minor  ", "minor")],
    )
    def test_case_and_space_are_normalised_not_degraded(self, raw, expected):
        """A recognisable severity must land on its own value, not the default."""
        finding = _Finding.model_validate({**_COMPLIANCE_FINDING, "severity": raw})

        assert finding.severity.value == expected

    def test_omitted_severity_still_defaults(self):
        node = {k: v for k, v in _COMPLIANCE_FINDING.items() if k != "severity"}

        assert _Finding.model_validate(node).severity.value == "minor"

    def test_grounding_constraints_are_untouched(self):
        """Coercing severity must not soften the #305 grounding gate."""
        for bad in ({"snippet": ""}, {"reason": ""}, {"line": 0}):
            with pytest.raises(ValueError):
                _Finding.model_validate({**_COMPLIANCE_FINDING, **bad})

    def test_mixed_response_no_longer_loses_the_compliance_finding(self):
        """The live failure: violation kept, compliance dropped, in one response."""
        violation = {**_COMPLIANCE_FINDING, "t": "violation", "severity": "major"}
        raw = json.dumps({"findings": [violation, _COMPLIANCE_FINDING]})

        findings, dropped = _parse_findings(raw)

        assert dropped == 0
        assert [f["severity"] for f in findings] == ["major", "minor"]
