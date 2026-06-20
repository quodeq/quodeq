from __future__ import annotations

from quodeq.analysis.mcp.schemas import (
    MARK_FILE_DONE_NAME,
    MARK_FILE_DONE_DESC,
    MARK_FILE_DONE_SCHEMA,
    REPORT_FINDING_SCHEMA,
)


class TestReportFindingSchema:
    def test_vt_is_optional_taxonomy_string(self):
        vt = REPORT_FINDING_SCHEMA["properties"]["vt"]
        assert vt["type"] == "string"
        assert "vt" not in REPORT_FINDING_SCHEMA["required"]

    def test_vt_description_mentions_taxonomy(self):
        desc = REPORT_FINDING_SCHEMA["properties"]["vt"]["description"].lower()
        assert "taxonomy" in desc


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
