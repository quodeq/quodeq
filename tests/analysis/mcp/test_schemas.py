from __future__ import annotations

from quodeq.analysis.mcp.schemas import (
    FINDING_TYPE_COMPLIANCE,
    FINDING_TYPE_VIOLATION,
    MARK_FILE_DONE_NAME,
    MARK_FILE_DONE_DESC,
    MARK_FILE_DONE_SCHEMA,
    REPORT_FINDING_SCHEMA,
    SEVERITY_CRITICAL,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
)


class TestReportFindingSchema:
    def test_vt_is_optional_taxonomy_string(self):
        vt = REPORT_FINDING_SCHEMA["properties"]["vt"]
        assert vt["type"] == "string"
        assert "vt" not in REPORT_FINDING_SCHEMA["required"]

    def test_vt_description_mentions_taxonomy(self):
        desc = REPORT_FINDING_SCHEMA["properties"]["vt"]["description"].lower()
        assert "taxonomy" in desc

    def test_t_enum_matches_the_finding_type_constants(self):
        assert REPORT_FINDING_SCHEMA["properties"]["t"]["enum"] == [
            FINDING_TYPE_VIOLATION, FINDING_TYPE_COMPLIANCE,
        ]

    def test_severity_enum_matches_the_severity_constants(self):
        assert REPORT_FINDING_SCHEMA["properties"]["severity"]["enum"] == [
            SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR,
        ]


class TestFindingTypeAndSeverityConstantsSharedAcrossGates:
    """scope_gate.py, provenance_gate.py, precedent_downweight.py and
    enricher.py all read/write the same report_finding dict this schema
    defines; each imports these constants from here rather than retyping
    "violation"/"major"/"minor"/"critical"."""

    def test_scope_gate_imports_the_shared_constants(self):
        from quodeq.analysis.mcp import scope_gate

        assert scope_gate.FINDING_TYPE_VIOLATION is FINDING_TYPE_VIOLATION
        assert scope_gate.SEVERITY_MAJOR is SEVERITY_MAJOR
        assert scope_gate.SEVERITY_MINOR is SEVERITY_MINOR

    def test_provenance_gate_imports_the_shared_constants(self):
        from quodeq.analysis.mcp import provenance_gate

        assert provenance_gate.FINDING_TYPE_VIOLATION is FINDING_TYPE_VIOLATION
        assert provenance_gate.SEVERITY_CRITICAL is SEVERITY_CRITICAL
        assert provenance_gate.SEVERITY_MAJOR is SEVERITY_MAJOR

    def test_precedent_downweight_imports_the_shared_constant(self):
        from quodeq.analysis.mcp import precedent_downweight

        assert precedent_downweight.FINDING_TYPE_VIOLATION is FINDING_TYPE_VIOLATION

    def test_enricher_imports_the_shared_constant(self):
        from quodeq.analysis.mcp import enricher

        assert enricher.FINDING_TYPE_VIOLATION is FINDING_TYPE_VIOLATION


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
