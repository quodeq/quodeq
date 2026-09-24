from __future__ import annotations

from quodeq.analysis.mcp.schemas import (
    MARK_FILE_DONE_NAME,
    MARK_FILE_DONE_DESC,
    MARK_FILE_DONE_SCHEMA,
    REPORT_FINDING_SCHEMA,
)
from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.severity import Severity


class TestReportFindingSchema:
    def test_vt_is_optional_taxonomy_string(self):
        vt = REPORT_FINDING_SCHEMA["properties"]["vt"]
        assert vt["type"] == "string"
        assert "vt" not in REPORT_FINDING_SCHEMA["required"]

    def test_vt_description_mentions_taxonomy(self):
        desc = REPORT_FINDING_SCHEMA["properties"]["vt"]["description"].lower()
        assert "taxonomy" in desc

    def test_t_enum_matches_the_finding_type_constants(self):
        assert REPORT_FINDING_SCHEMA["properties"]["t"]["enum"] == ["violation", "compliance"]

    def test_severity_enum_matches_the_severity_constants(self):
        assert REPORT_FINDING_SCHEMA["properties"]["severity"]["enum"] == [
            s.value for s in Severity
        ]


class TestFindingTypeAndSeverityConstantsSharedAcrossGates:
    """scope_gate.py, provenance_gate.py, precedent_downweight.py and
    enricher.py all read/write the same report_finding dict this schema
    defines; each imports FindingType from core.types.finding_type (rather
    than retyping "violation") and Severity straight from core.types.severity."""

    def test_scope_gate_imports_the_shared_constants(self):
        from quodeq.analysis.mcp import scope_gate

        assert scope_gate.FindingType is FindingType
        assert scope_gate.Severity is Severity

    def test_provenance_gate_imports_the_shared_constants(self):
        from quodeq.analysis.mcp import provenance_gate

        assert provenance_gate.FindingType is FindingType
        assert provenance_gate.Severity is Severity

    def test_precedent_downweight_imports_the_shared_constant(self):
        from quodeq.analysis.mcp import precedent_downweight

        assert precedent_downweight.FindingType is FindingType

    def test_enricher_imports_the_shared_constant(self):
        from quodeq.analysis.mcp import enricher

        assert enricher.FindingType is FindingType


class TestMarkFileDoneSchema:
    def test_name_is_stable(self):
        assert MARK_FILE_DONE_NAME == "mark_file_done"

    def test_required_fields(self):
        assert set(MARK_FILE_DONE_SCHEMA["required"]) == {"file", "status"}

    def test_status_enum(self):
        assert MARK_FILE_DONE_SCHEMA["properties"]["status"]["enum"] == ["ok", "error"]

    def test_reason_is_optional_free_string(self):
        reason = MARK_FILE_DONE_SCHEMA["properties"]["reason"]
        assert reason["type"] == "string"
        assert "reason" not in MARK_FILE_DONE_SCHEMA["required"]

    def test_description_mentions_per_file_completion(self):
        assert "after" in MARK_FILE_DONE_DESC.lower()
        assert "file" in MARK_FILE_DONE_DESC.lower()
