"""Totals.violations_per100_files survives report read-back and recount."""
from quodeq.core.types.finding import Finding
from quodeq.data.mappers._mapper_findings import parse_totals
from quodeq.services.dismissed import recount_totals


def test_parse_totals_reads_density():
    t = parse_totals({"violationCount": 3, "complianceCount": 1,
                      "severity": {"major": 1}, "violationsPer100Files": 37.5})
    assert t.violations_per100_files == 37.5


def test_parse_totals_density_absent_is_none():
    assert parse_totals({"violationCount": 3}).violations_per100_files is None


def test_recount_totals_recomputes_density():
    v = [Finding(practice_id="FT", verdict="violation", severity="major")] * 3
    assert recount_totals(v, compliance_count=0, files_read=8).violations_per100_files == 37.5
    assert recount_totals(v, compliance_count=0).violations_per100_files is None
