"""The accumulated view built from score-cache rows (``scoring/_accumulated_rows``)."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.run.state import RunState
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.core.types import DimensionResult, Totals
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.scoring import (
    AccumulatedScope,
    build_accumulated_from_rows,
    run_rows,
    runs_as_of,
)
from quodeq.services.suppression_keys import SuppressionKeys

NEW = RunInfo(run_id="r-new", date_iso="2026-02-01", date_label="2026-02-01", status=RunState.DONE)
OLD = RunInfo(run_id="r-old", date_iso="2026-01-01", date_label="2026-01-01", status=RunState.DONE)
RUNNING = RunInfo(run_id="r-run", date_iso="2026-03-01", date_label="2026-03-01", status=RunState.RUNNING)


def _finding(line: int) -> Finding:
    return Finding(practice_id="P1", verdict="violation", file="a.py", line=line, req="R1", severity="major")


def _row(name: str, score: str, files_read: int | None = 10) -> DimensionResult:
    return DimensionResult(
        dimension=name, overall_score=score, overall_grade="Fair", files_read=files_read,
        principles=[PrincipleGrade("P1", score, "Fair")],
    )


FULL = {
    "r-new": [DimensionResult(
        dimension="security", overall_score="5.0/10", overall_grade="Poor", files_read=10,
        principles=[PrincipleGrade("P1", "5.0/10", "Poor")],
        violations=[_finding(1), _finding(2)],
        totals=Totals(violation_count=2, compliance_count=3),
    )],
    "r-old": [DimensionResult(
        dimension="security", overall_score="4.0/10", overall_grade="Poor",
        violations=[_finding(1), _finding(2), _finding(3)],
    )],
}
ROWS = {"r-new": [_row("security", "7.0/10")], "r-old": [_row("security", "6.0/10")]}


class _Fetcher:
    def __init__(self) -> None:
        self.row_calls: list[str] = []

    def __call__(self, run_id: str) -> list[DimensionResult]:
        raise AssertionError("the walk must read rows, not the trend shape")

    def rows(self, run_id: str) -> list[DimensionResult]:
        self.row_calls.append(run_id)
        return ROWS.get(run_id, [])


def _full(run_id: str) -> list[DimensionResult]:
    return FULL.get(run_id, [])


def _scope(tmp_path: Path, dismissed: set | None = None) -> AccumulatedScope:
    (tmp_path / "proj").mkdir(exist_ok=True)
    return AccumulatedScope(tmp_path, "proj", DEFAULT_PARAMS, SuppressionKeys(dismissed or set(), set()))


def test_runs_as_of_cuts_at_the_named_run_and_yields_nothing_for_an_unknown_one():
    assert runs_as_of([NEW, OLD], None) == [NEW, OLD]
    assert runs_as_of([NEW, OLD], "r-old") == [OLD]
    assert runs_as_of([NEW, OLD], "2026-01-15") == []


def test_run_rows_falls_back_to_a_plain_callable():
    plain = lambda run_id: []  # noqa: E731
    assert run_rows(plain) is plain
    fetcher = _Fetcher()
    assert run_rows(fetcher) == fetcher.rows


def test_an_untouched_winner_is_served_as_read(tmp_path):
    fetcher = _Fetcher()
    payload, complete = build_accumulated_from_rows(_scope(tmp_path), [NEW, OLD], fetcher, _full)

    (dim,) = payload["dimensions"]
    assert complete
    assert fetcher.row_calls == ["r-new", "r-old"]
    assert dim["fromRunId"] == "r-new" and dim["fromDateIso"] == "2026-02-01"
    assert len(dim["violations"]) == 2
    assert dim["overallScore"] == "5.0/10" and dim["totals"]["complianceCount"] == 3
    # The previous occurrence comes from the rows, not a second full read.
    assert dim["previousRunId"] == "r-old" and dim["previousScore"] == "6.0/10"
    assert payload["summary"]["previousNumericAverage"] == pytest.approx(6.0)


def test_a_touched_winner_keeps_its_findings_minus_the_suppressed_and_takes_the_row_grade(tmp_path):
    scope = _scope(tmp_path, dismissed={("R1", "a.py", 1)})
    payload, complete = build_accumulated_from_rows(scope, [NEW, OLD], _Fetcher(), _full)

    (dim,) = payload["dimensions"]
    assert complete
    assert [v["line"] for v in dim["violations"]] == [2]
    assert dim["overallScore"] == "7.0/10" and dim["overallGrade"] == "Fair"
    assert dim["principles"] == [{"principle": "P1", "score": "7.0/10", "grade": "Fair"}]
    assert dim["totals"]["violationCount"] == 1 and dim["totals"]["complianceCount"] == 3
    assert dim["totals"]["severity"]["major"] == 1
    assert payload["summary"]["totalViolations"] == 1
    assert payload["summary"]["numericAverage"] == pytest.approx(7.0)


def test_a_winner_whose_full_read_lacks_the_dimension_marks_the_payload_incomplete(tmp_path):
    payload, complete = build_accumulated_from_rows(
        _scope(tmp_path), [NEW, OLD], _Fetcher(), lambda _run_id: [])

    (dim,) = payload["dimensions"]
    assert not complete
    assert dim["overallScore"] == "7.0/10" and dim["violations"] == []


def test_a_zero_coverage_row_is_skipped_for_an_older_valid_one(tmp_path):
    rows = {"r-new": [_row("security", "9.0/10", files_read=0)], "r-old": [_row("security", "6.0/10")]}
    fetcher = _Fetcher()
    fetcher.rows = lambda run_id: rows.get(run_id, [])  # type: ignore[method-assign]
    payload, _ = build_accumulated_from_rows(_scope(tmp_path), [NEW, OLD], fetcher, _full)

    (dim,) = payload["dimensions"]
    assert dim["fromRunId"] == "r-old" and dim["overallScore"] == "4.0/10"


def test_running_runs_never_feed_the_view(tmp_path):
    payload, complete = build_accumulated_from_rows(_scope(tmp_path), [RUNNING], _Fetcher(), _full)
    assert (payload, complete) == ({"dimensions": [], "summary": {}}, True)
