"""Round-trip tests: DTO -> to_camel_dict -> parse_* -> assert equality."""

from __future__ import annotations

from quodeq.core.types import to_camel_dict
from quodeq.core.types.mappers import (
    parse_dimension_result,
    parse_dimension_summary,
    parse_finding,
    parse_job_snapshot,
    parse_parsed_report,
    parse_plugin_info,
    parse_project_entry,
    parse_trend_point,
    parse_violation_response,
    parse_violation_summary,
)

from tests.core.test_types import (
    DIMENSION_RESULT,
    DIMENSION_SUMMARY,
    FINDING,
    JOB_SNAPSHOT,
    PARSED_REPORT,
    PLUGIN_INFO,
    PROJECT_ENTRY,
    TREND_POINT,
    VIOLATION_RESPONSE,
    VIOLATION_SUMMARY,
)


class TestRoundTrip:
    def test_finding(self) -> None:
        raw = to_camel_dict(FINDING)
        assert isinstance(raw, dict)
        assert parse_finding(raw) == FINDING

    def test_dimension_result(self) -> None:
        raw = to_camel_dict(DIMENSION_RESULT)
        assert isinstance(raw, dict)
        assert parse_dimension_result(raw) == DIMENSION_RESULT

    def test_parsed_report(self) -> None:
        raw = to_camel_dict(PARSED_REPORT)
        assert isinstance(raw, dict)
        assert parse_parsed_report(raw) == PARSED_REPORT

    def test_dimension_summary(self) -> None:
        raw = to_camel_dict(DIMENSION_SUMMARY)
        assert isinstance(raw, dict)
        assert parse_dimension_summary(raw) == DIMENSION_SUMMARY

    def test_project_entry(self) -> None:
        raw = to_camel_dict(PROJECT_ENTRY)
        assert isinstance(raw, dict)
        assert parse_project_entry(raw) == PROJECT_ENTRY

    def test_job_snapshot(self) -> None:
        raw = to_camel_dict(JOB_SNAPSHOT)
        assert isinstance(raw, dict)
        assert parse_job_snapshot(raw) == JOB_SNAPSHOT

    def test_plugin_info(self) -> None:
        raw = to_camel_dict(PLUGIN_INFO)
        assert isinstance(raw, dict)
        assert parse_plugin_info(raw) == PLUGIN_INFO

    def test_violation_response(self) -> None:
        raw = to_camel_dict(VIOLATION_RESPONSE)
        assert isinstance(raw, dict)
        assert parse_violation_response(raw) == VIOLATION_RESPONSE

    def test_violation_summary(self) -> None:
        raw = to_camel_dict(VIOLATION_SUMMARY)
        assert isinstance(raw, dict)
        assert parse_violation_summary(raw) == VIOLATION_SUMMARY

    def test_trend_point(self) -> None:
        raw = to_camel_dict(TREND_POINT)
        assert isinstance(raw, dict)
        assert parse_trend_point(raw) == TREND_POINT
