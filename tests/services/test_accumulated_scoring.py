"""Tests for quodeq.services.accumulated — scoring helpers.

Split from test_accumulated.py: the coverage-0 stub exclusion,
numeric_average, and _aggregate_severity_counts. Shared builders live in
tests/services/_accumulated_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services.accumulated import _aggregate_severity_counts, numeric_average

from tests.services._accumulated_fixtures import _dim


class TestZeroCoverageStubExcluded:
    """A cancelled run's coverage-0 stub eval (filesRead=0) must not drive
    the accumulated Overview. _score_completed_evidence can write such a stub
    at cancel time when no findings landed; its score is meaningless. The
    accumulated reader falls through to an older run with real coverage."""

    def _info(self, run_id):
        from quodeq.data.fs.report_parser.runs import RunInfo
        return RunInfo(run_id=run_id, date_iso="2024-01-01", date_label="Jan 01")

    def test_zero_files_read_dim_falls_through_to_real_run(self):
        from quodeq.services._accumulated_data import _read_all_run_data
        stub = _dim("security", "9.9", "A", filesRead=0)   # coverage-0 stub, newest
        real = _dim("security", "6.0", "C", filesRead=5)   # real, older
        fetch = {"r2": [stub], "r1": [real]}
        latest, _prev, _prev_run = _read_all_run_data(
            Path("/x"), "proj", [self._info("r2"), self._info("r1")],
            ["r2", "r1"], get_run_data=lambda rid: fetch[rid],
        )
        assert latest["security"].overall_score == "6.0"

    def test_missing_files_read_is_still_trusted(self):
        # Legacy evals carry no filesRead (None); those must stay valid.
        from quodeq.services._accumulated_data import _read_all_run_data
        legacy = _dim("security", "8.0", "A")  # no filesRead field
        fetch = {"r1": [legacy]}
        latest, _p, _pr = _read_all_run_data(
            Path("/x"), "proj", [self._info("r1")], ["r1"],
            get_run_data=lambda rid: fetch[rid],
        )
        assert latest["security"].overall_score == "8.0"


class TestNumericAverage:
    def test_computes_average(self):
        """Two dimensions with scores 8.0 and 6.0 should average to 7.0."""
        dims = [_dim("a", "8.0"), _dim("b", "6.0")]
        assert numeric_average(dims) == 7.0

    def test_returns_none_for_empty(self):
        assert numeric_average([]) is None

    def test_skips_none_scores(self):
        dims = [_dim("a", "8.0"), DimensionResult(dimension="b", overall_score=None)]
        assert numeric_average(dims) == 8.0

    def test_handles_grade_strings(self):
        dims = [_dim("a", "A"), _dim("b", "9.0")]
        # "A" is not numeric, should be skipped
        result = numeric_average(dims)
        assert result == 9.0

    def test_all_non_numeric_returns_none(self):
        dims = [_dim("a", "A"), _dim("b", "B+")]
        assert numeric_average(dims) is None

    def test_single_dimension(self):
        dims = [_dim("a", "10.0")]
        assert numeric_average(dims) == 10.0


class TestAggregateSeverityCounts:
    def test_sums_across_dimensions(self):
        dims = [
            _dim("a", totals={"violationCount": 3, "complianceCount": 5, "severity": {"critical": 1, "major": 1, "minor": 1}}),
            _dim("b", totals={"violationCount": 2, "complianceCount": 1, "severity": {"critical": 0, "major": 2, "minor": 0}}),
        ]
        result = _aggregate_severity_counts(dims)
        assert result["totalViolations"] == 5
        assert result["totalCompliance"] == 6
        assert result["critical"] == 1
        assert result["major"] == 3
        assert result["minor"] == 1

    def test_handles_missing_totals(self):
        dims = [_dim("a")]
        result = _aggregate_severity_counts(dims)
        assert result["totalViolations"] == 0

    def test_empty_list(self):
        result = _aggregate_severity_counts([])
        assert result["totalViolations"] == 0
        assert result["critical"] == 0
