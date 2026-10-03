"""Tests for _fs_metadata.py — the project card's default-view-runs selection.

The repositories card must consult the same run set as the Overview
(select_default_view_runs), not just iterate all runs newest-first.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.state import RunState
from quodeq.core.types import DimensionResult
from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services._fs_metadata import read_accumulated_summary

from tests.services.conftest import stub_row_fetcher


def _security(score: str, grade: str, files_read: int) -> DimensionResult:
    return DimensionResult(dimension="security", overall_score=score, overall_grade=grade,
                           files_read=files_read, source_file_count=10)


class TestCardUsesDefaultViewRuns:
    def test_newer_noncomplete_run_does_not_drive_the_card(self, monkeypatch):
        """The repositories card must consult the same run set as the
        Overview (select_default_view_runs). It used to iterate ALL runs
        newest-first, so a newer cancelled/failed run gave the card a
        different grade than the Overview showed after clicking in.
        """
        fetched = stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_security("7.0/10", "B", 5)])
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-03", date_label="Jan 03", status=RunState.CANCELLED),
            RunInfo(run_id="run-failed", date_iso="2026-01-02", date_label="Jan 02", status=RunState.FAILED),
            RunInfo(run_id="run-complete", date_iso="2026-01-01", date_label="Jan 01", status=RunState.DONE),
        ]
        grade, score, files, _pending = read_accumulated_summary(
            Path("/r"), "proj-card-eligibility", runs, cache_enabled=False,
        )
        assert set(fetched) == {"run-complete"}, (
            f"card must read only the default-view run set, got: {set(fetched)}"
        )
        assert (grade, score, files) == ("Good", 7.0, 10)

    def test_card_falls_back_to_cancelled_when_no_complete_run(self, monkeypatch):
        fetched = stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_security("6.0/10", "C", 5)])
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-02", date_label="Jan 02", status=RunState.CANCELLED),
            RunInfo(run_id="run-failed", date_iso="2026-01-01", date_label="Jan 01", status=RunState.FAILED),
        ]
        grade, score, _files, _pending = read_accumulated_summary(
            Path("/r"), "proj-card-fallback", runs, cache_enabled=False,
        )
        assert set(fetched) == {"run-cancelled"}
        assert score == 6.0

    def test_card_skips_zero_coverage_stub_like_the_overview(self, monkeypatch):
        """A newer cancelled run's coverage-0 stub (filesRead=0) must not
        drive the project card, exactly like the accumulated Overview. The
        card falls through to the real older run's score."""
        per_run = {
            "run-stub": [_security("9.9/10", "A", 0)],
            "run-real": [_security("6.0/10", "C", 5)],
        }
        stub_row_fetcher(monkeypatch, lambda root, proj, rid: per_run[rid])
        runs = [
            RunInfo(run_id="run-stub", date_iso="2026-01-02", date_label="Jan 02", status=RunState.CANCELLED),
            RunInfo(run_id="run-real", date_iso="2026-01-01", date_label="Jan 01", status=RunState.CANCELLED),
        ]
        _grade, score, _files, _pending = read_accumulated_summary(
            Path("/r"), "proj-card-stub", runs, cache_enabled=False,
        )
        assert score == 6.0, f"card took the coverage-0 stub, got {score}"

    def test_card_reads_no_report_when_rows_carry_the_file_count(self, monkeypatch):
        """Rows are all the card needs: no full read, no evidence manifest."""
        stub_row_fetcher(monkeypatch, lambda root, proj, rid: [_security("8.0/10", "A", 5)])

        def _no_manifest(run_dir):
            raise AssertionError(f"manifest read for {run_dir}")

        monkeypatch.setattr("quodeq.services._accumulated_data.run_source_file_count", _no_manifest)
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01", status=RunState.DONE)]
        _grade, _score, files, _pending = read_accumulated_summary(
            Path("/r"), "proj-card-rows-only", runs, cache_enabled=False,
        )
        assert files == 10
