"""Tests for _fs_metadata.py — the project card's default-view-runs selection.

Split from test_fs_metadata.py (further split out of
test_fs_metadata_accumulated.py to stay under the file-size cap): the
repositories card must consult the same run set as the Overview
(select_default_view_runs), not just iterate all runs newest-first.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.services._fs_metadata import _read_accumulated_summary


class TestCardUsesDefaultViewRuns:
    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_newer_noncomplete_run_does_not_drive_the_card(
        self, mock_read, mock_summarize, monkeypatch,
    ):
        """The repositories card must consult the same run set as the
        Overview (select_default_view_runs). It used to iterate ALL runs
        newest-first, so a newer cancelled/failed run gave the card a
        different grade than the Overview showed after clicking in.
        """
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="7.0/10",
                            overall_grade="B", files_read=5, source_file_count=5),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "B", "numeric_average": 7.0},
        )()
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-03", date_label="Jan 03", status="cancelled"),
            RunInfo(run_id="run-failed", date_iso="2026-01-02", date_label="Jan 02", status="failed"),
            RunInfo(run_id="run-complete", date_iso="2026-01-01", date_label="Jan 01", status="complete"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-eligibility", runs,
        )
        read_run_ids = {call.args[2] for call in mock_read.call_args_list}
        assert read_run_ids == {"run-complete"}, (
            "card must read only the default-view run set, got: "
            f"{read_run_ids}"
        )
        assert grade == "B"

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_falls_back_to_cancelled_when_no_complete_run(
        self, mock_read, mock_summarize, monkeypatch,
    ):
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="6.0/10",
                            overall_grade="C", files_read=5, source_file_count=5),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "C", "numeric_average": 6.0},
        )()
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-02", date_label="Jan 02", status="cancelled"),
            RunInfo(run_id="run-failed", date_iso="2026-01-01", date_label="Jan 01", status="failed"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-fallback", runs,
        )
        read_run_ids = {call.args[2] for call in mock_read.call_args_list}
        assert read_run_ids == {"run-cancelled"}
        assert grade == "C"

    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_skips_zero_coverage_stub_like_the_overview(
        self, mock_read, monkeypatch,
    ):
        """A newer cancelled run's coverage-0 stub (filesRead=0) must not
        drive the project card, exactly like the accumulated Overview. The
        card fell through to the real older run's score."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        per_run = {
            "run-stub": [DimensionResult(
                dimension="security", overall_score="9.9/10", overall_grade="A",
                files_read=0, source_file_count=10,
            )],
            "run-real": [DimensionResult(
                dimension="security", overall_score="6.0/10", overall_grade="C",
                files_read=5, source_file_count=10,
            )],
        }
        mock_read.side_effect = lambda root, proj, run_id: per_run[run_id]
        runs = [
            RunInfo(run_id="run-stub", date_iso="2026-01-02", date_label="Jan 02", status="cancelled"),
            RunInfo(run_id="run-real", date_iso="2026-01-01", date_label="Jan 01", status="cancelled"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-stub", runs,
        )
        # The card score must be the real run's 6.0, not the stub's 9.9.
        assert score == 6.0, f"card took the coverage-0 stub, got {score}"
