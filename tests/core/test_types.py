"""DTO fixtures and serialization/error-handling tests for quodeq.core.types."""

from __future__ import annotations

import pytest

from quodeq.core.types import (
    DimensionResult,
    DimensionSummary,
    Finding,
    GradeBreakdown,
    JobSnapshot,
    ParsedReport,
    PluginDimension,
    PluginInfo,
    PrincipleGrade,
    ProjectEntry,
    ReqRef,
    SeverityTally,
    Totals,
    TrendPoint,
    ViolationResponse,
    ViolationSummary,
    to_camel_dict,
)
from quodeq.core.types.mappers import (
    parse_dimension_result,
    parse_finding,
    parse_job_snapshot,
    parse_plugin_info,
    parse_project_entry,
    parse_trend_point,
    parse_violation_response,
)
from quodeq.core.types.violation import ProgressInfo, ViolationFileEntry


# ---------------------------------------------------------------------------
# Fixtures — realistic DTO instances
# ---------------------------------------------------------------------------

FINDING = Finding(
    principle="Naming",
    file="src/app.py",
    line=42,
    title="Bad variable name",
    reason="Name 'x' is too short",
    snippet="x = 1",
    severity="major",
    cwe=123,
    req="REQ-01",
    req_refs=[ReqRef(label="CWE-123", url="https://cwe.mitre.org/123")],
    dimension="maintainability",
    violation_type="style",
)

TOTALS = Totals(
    violation_count=5,
    compliance_count=10,
    severity=SeverityTally(critical=1, major=2, minor=2, unknown=0),
)

PRINCIPLE = PrincipleGrade(name="Naming", score="85", grade="B")

DIMENSION_RESULT = DimensionResult(
    dimension="maintainability",
    overall_score="78",
    overall_grade="C",
    principles=[PRINCIPLE],
    violations=[FINDING],
    compliance=[],
    totals=TOTALS,
    source_file_count=12,
    evidence_date="2026-03-15",
    discipline="python",
    trend="up",
    previous_run_id="run-001",
    previous_score="70",
    stale=False,
    from_run_id="run-002",
    from_date_iso="2026-03-14",
    from_date_label="Mar 14",
    run_id="run-003",
)

PARSED_REPORT = ParsedReport(
    dimension="security",
    overall_score="90",
    overall_grade="A",
    principles=[PRINCIPLE],
    detail_principles=[],
    violations=[FINDING],
    compliance=[],
    totals=TOTALS,
)

DIMENSION_SUMMARY = DimensionSummary(
    dimensions_count=3,
    overall_grade="B",
    numeric_average=82.5,
    grade_breakdown=[GradeBreakdown(grade="A", count=1), GradeBreakdown(grade="B", count=2)],
)

PROJECT_ENTRY = ProjectEntry(
    id="proj-1",
    name="my-project",
    parent="org",
    display_name="My Project",
    discipline="python",
    path="/code/my-project",
    location="local",
    runs_count=5,
    latest_run_id="run-005",
    latest_date="2026-03-15",
    path_exists=True,
    files_count=100,
    latest_grade="B",
    latest_score=82.0,
)

JOB_SNAPSHOT = JobSnapshot(
    job_id="job-1",
    status="running",
    command="analyze",
    started_at="2026-03-15T10:00:00Z",
    ended_at=None,
    exit_code=None,
    logs=["Starting analysis", "Reading files"],
    output_project="my-project",
    output_run_id="run-005",
    phase="evaluation",
    current_dimension="security",
    dimensions=["security", "maintainability"],
    error=None,
)

PLUGIN_INFO = PluginInfo(
    id="python",
    name="Python Analyzer",
    extensions=[".py", ".pyi"],
    dimensions=[
        PluginDimension(id="maintainability", weight=2, iso_25010="Maintainability"),
        PluginDimension(id="security", weight=1, iso_25010=None),
    ],
)

VIOLATION_RESPONSE = ViolationResponse(
    dimension="security",
    run_id="run-005",
    project="my-project",
    violations=[FINDING],
    compliance=[],
    partial=True,
    progress=ProgressInfo(files_read=10, violations=3, compliance=7),
)

VIOLATION_SUMMARY = ViolationSummary(
    total=10,
    critical=2,
    major=4,
    minor=4,
    files=[
        ViolationFileEntry(path="src/app.py", count=5, critical=1, major=2, minor=2),
        ViolationFileEntry(path="src/util.py", count=5, critical=1, major=2, minor=2),
    ],
)

TREND_POINT = TrendPoint(
    run_id="run-003",
    date_iso="2026-03-15",
    date_label="Mar 15",
    dimensions_count=4,
    overall_grade="B",
    numeric_average=80.0,
)


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestToCamelDict:
    def test_omits_none_fields(self) -> None:
        finding = Finding(severity="minor")
        raw = to_camel_dict(finding)
        assert isinstance(raw, dict)
        assert "principle" not in raw
        assert "file" not in raw
        assert "severity" in raw

    def test_snake_to_camel(self) -> None:
        raw = to_camel_dict(TOTALS)
        assert isinstance(raw, dict)
        assert "violationCount" in raw
        assert "complianceCount" in raw
        assert "violation_count" not in raw


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    def test_dimension_result_missing_dimension(self) -> None:
        with pytest.raises(TypeError, match="dimension must be str"):
            parse_dimension_result({"overallScore": "80"})

    def test_job_snapshot_missing_job_id(self) -> None:
        with pytest.raises(TypeError, match="jobId must be str"):
            parse_job_snapshot({"status": "running"})

    def test_job_snapshot_missing_status(self) -> None:
        with pytest.raises(TypeError, match="status must be str"):
            parse_job_snapshot({"jobId": "j1"})

    def test_plugin_info_missing_id(self) -> None:
        with pytest.raises(TypeError, match="id must be str"):
            parse_plugin_info({"name": "x"})

    def test_plugin_info_missing_name(self) -> None:
        with pytest.raises(TypeError, match="name must be str"):
            parse_plugin_info({"id": "x"})

    def test_project_entry_missing_id(self) -> None:
        with pytest.raises(TypeError, match="id must be str"):
            parse_project_entry({"name": "x"})

    def test_project_entry_missing_name(self) -> None:
        with pytest.raises(TypeError, match="name must be str"):
            parse_project_entry({"id": "x"})

    def test_violation_response_missing_dimension(self) -> None:
        with pytest.raises(TypeError, match="dimension must be str"):
            parse_violation_response({"runId": "r", "project": "p"})

    def test_trend_point_missing_run_id(self) -> None:
        with pytest.raises(TypeError, match="runId must be str"):
            parse_trend_point({})

    def test_finding_with_defaults(self) -> None:
        """Finding has no required fields — empty dict should produce defaults."""
        result = parse_finding({})
        assert result.severity == "minor"
        assert result.principle is None
        assert result.req_refs == []
