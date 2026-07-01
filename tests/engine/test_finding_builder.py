"""Tests for finding_builder — FindingSpec and build_finding_base."""
from __future__ import annotations

import pytest

from quodeq.core.finding_builder import (
    FindingSpec,
    ViolationContext,
    build_finding_base,
    format_file_line,
)
from quodeq.core.types import Finding, ReqRef


class TestBuildFindingBase:
    def test_minimal_spec(self):
        spec = FindingSpec(practice_id="P1")
        finding = build_finding_base(spec)
        assert isinstance(finding, Finding)
        assert finding.practice_id == "P1"
        assert finding.severity == "minor"
        assert finding.file is None
        assert finding.req_refs == []

    def test_full_spec(self):
        spec = FindingSpec(
            practice_id="Auth",
            file="app.py",
            line=42,
            end_line=50,
            title="Missing auth check",
            reason="No authorization guard",
            snippet="def handler():",
            severity="critical",
            cwe=287,
            req="V2.1.1",
            req_refs=[{"label": "OWASP", "url": "https://owasp.org"}],
            context="API endpoint",
            scope="src/",
        )
        finding = build_finding_base(spec)
        assert finding.practice_id == "Auth"
        assert finding.file == "app.py"
        assert finding.line == 42
        assert finding.end_line == 50
        assert finding.severity == "critical"
        assert finding.cwe == 287
        assert finding.req == "V2.1.1"
        assert len(finding.req_refs) == 1
        assert finding.req_refs[0].label == "OWASP"
        assert finding.context == "API endpoint"
        assert finding.scope == "src/"

    def test_provenance_downgrade_carried(self):
        # Issue #656: the violations-parsing path must preserve the gate's marker.
        spec = FindingSpec(practice_id="P1", provenance_downgrade=True)
        assert build_finding_base(spec).provenance_downgrade is True

    def test_provenance_downgrade_defaults_false(self):
        assert build_finding_base(FindingSpec(practice_id="P1")).provenance_downgrade is False

    def test_severity_defaults_minor_when_none(self):
        spec = FindingSpec(practice_id="P1", severity=None)
        finding = build_finding_base(spec)
        assert finding.severity == "minor"

    def test_severity_not_included(self):
        spec = FindingSpec(practice_id="P1", severity="critical", include_severity=False)
        finding = build_finding_base(spec)
        assert finding.severity == "minor"  # include_severity=False forces "minor"

    def test_empty_cwe_becomes_none(self):
        spec = FindingSpec(practice_id="P1", cwe=0)
        finding = build_finding_base(spec)
        assert finding.cwe is None

    def test_empty_req_becomes_none(self):
        spec = FindingSpec(practice_id="P1", req="")
        finding = build_finding_base(spec)
        assert finding.req is None

    def test_empty_context_becomes_none(self):
        spec = FindingSpec(practice_id="P1", context="")
        finding = build_finding_base(spec)
        assert finding.context is None

    def test_empty_scope_becomes_none(self):
        spec = FindingSpec(practice_id="P1", scope="")
        finding = build_finding_base(spec)
        assert finding.scope is None

    def test_multiple_req_refs(self):
        spec = FindingSpec(
            practice_id="P1",
            req_refs=[
                {"label": "A", "url": "https://a.com"},
                {"label": "B", "url": "https://b.com"},
            ],
        )
        finding = build_finding_base(spec)
        assert len(finding.req_refs) == 2
        assert finding.req_refs[1].url == "https://b.com"

    def test_req_refs_missing_keys(self):
        spec = FindingSpec(practice_id="P1", req_refs=[{}])
        finding = build_finding_base(spec)
        assert finding.req_refs[0].label == ""
        assert finding.req_refs[0].url == ""


class TestFormatFileLine:
    def test_file_and_line(self):
        assert format_file_line("app.py", 42) == "app.py:42"

    def test_file_only(self):
        assert format_file_line("app.py", None) == "app.py"

    def test_none_file(self):
        assert format_file_line(None, 42) is None

    def test_both_none(self):
        assert format_file_line(None, None) is None

    def test_string_line(self):
        assert format_file_line("app.py", "10") == "app.py:10"


class TestViolationContext:
    def test_is_frozen(self):
        ctx = ViolationContext(project="proj", run_id="run-1", dimension="security")
        assert ctx.project == "proj"
        assert ctx.run_id == "run-1"
        assert ctx.dimension == "security"
        with pytest.raises(AttributeError):
            ctx.project = "other"
