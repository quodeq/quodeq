"""Tests for quodeq.services.dashboard — build_dashboard core behavior.

Split from test_dashboard.py: empty/missing-run handling, latest-run
selection among cancelled/failed/complete runs, explicit selection, the
too-new/corrupt evaluation.db SQL-overlay fallback, and the history-scalar
read path. The SQL-overlay contract and the dismissed/history-slimming
tests are split further into test_dashboard_build_sql_overlay.py and
test_dashboard_build_filtering.py to stay under the file-size cap. Shared
builders live in tests/services/_dashboard_fixtures.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.core.types import DimensionSummary
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.dashboard import build_dashboard
from tests.services._dashboard_fixtures import _dim, _make_run


class TestBuildDashboard:
    def test_returns_empty_when_no_runs(self, tmp_path):
        with patch("quodeq.services.dashboard.list_runs", return_value=[]):
            result = build_dashboard(str(tmp_path), "proj", "latest")
            assert result["dimensions"] == []
            assert result["selectedRun"] is None

    def test_raises_when_run_not_found(self, tmp_path):
        with patch("quodeq.services.dashboard.list_runs", return_value=[_make_run("r1")]):
            with pytest.raises(FileNotFoundError, match="Run not found"):
                build_dashboard(str(tmp_path), "proj", "nonexistent")

    def test_builds_dashboard_for_latest(self, tmp_path):
        run = _make_run("r1", "2024-01-01")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[run]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["project"] == "proj"
        assert result["selectedRun"]["runId"] == "r1"
        assert len(result["dimensions"]) == 1
        assert "trend" in result

    def test_build_dashboard_survives_too_new_db(self, tmp_path):
        """The SQL grade override reads the per-run evaluation.db. If that DB was
        written by a newer Quodeq, build_dashboard must keep the FS-based grades
        instead of crashing on SchemaVersionError."""
        import sqlite3

        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.data.events.writer import EventLogWriter
        from quodeq.data.projection.projector import Projector
        from quodeq.data.sqlite._schema import SCHEMA_VERSION

        run_dir = tmp_path / "proj" / "r1"
        run_dir.mkdir(parents=True)
        log = run_dir / "events.jsonl"
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1",
        )))
        Projector().ensure_projected(log, run_dir, project_dir=tmp_path / "proj")
        conn = sqlite3.connect(run_dir / "evaluation.db")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
        conn.commit()
        conn.close()

        run = _make_run("r1", "2024-01-01")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[run]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")  # must not raise

        # The FS-based grades survive: the SQL override is skipped, not silently
        # blanked, so the dimension keeps the grade/score from read_run_data.
        assert len(result["dimensions"]) == 1
        dim = result["dimensions"][0]
        assert dim["overallGrade"] == "B"
        assert dim["overallScore"] == "7.0"

    def test_build_dashboard_survives_corrupt_db(self, tmp_path):
        """If the per-run evaluation.db is corrupt or half-written it raises a
        generic sqlite3.DatabaseError, not SchemaVersionError. The SQL grade
        override must keep the FS-based grades instead of crashing the dashboard
        build. Widening the seam to DatabaseError (which SchemaVersionError
        subclasses) covers both the too-new and the corrupt case."""
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.data.events.writer import EventLogWriter

        run_dir = tmp_path / "proj" / "r1"
        run_dir.mkdir(parents=True)
        log = run_dir / "events.jsonl"
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1",
        )))
        # A truncated / non-SQLite evaluation.db: opening it raises
        # "file is not a database" when the override path tries to project.
        (run_dir / "evaluation.db").write_bytes(b"this is not a sqlite database")

        run = _make_run("r1", "2024-01-01")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[run]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")  # must not raise

        assert len(result["dimensions"]) == 1
        dim = result["dimensions"][0]
        assert dim["overallGrade"] == "B"
        assert dim["overallScore"] == "7.0"

    def test_latest_skips_cancelled_runs(self, tmp_path):
        # ``"latest"`` defaults to the most recent fully-completed run so the
        # per-dim cards reflect a coherent run that agrees with the headline.
        # The cancelled run remains reachable via explicit selection.
        cancelled = RunInfo(run_id="r-newest", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        complete = RunInfo(run_id="r-older", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled, complete]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r-older"

    def test_latest_falls_back_when_all_cancelled(self, tmp_path):
        # If every run is cancelled, fall back to the newest one rather than
        # refusing to render — the dashboard still needs to show something.
        cancelled1 = RunInfo(run_id="r2", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        cancelled2 = RunInfo(run_id="r1", date_iso="2024-02-01", date_label="2024-02-01", status="cancelled")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled1, cancelled2]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r2"

    def test_latest_prefers_cancelled_over_newer_failed(self, tmp_path):
        # A failed run must not headline the dashboard while a cancelled run
        # (with real kept-findings data) exists — mirror the Overview's
        # select_default_view_runs rule so the two surfaces agree.
        failed = RunInfo(run_id="r-failed", date_iso="2024-03-01", date_label="2024-03-01", status="failed")
        cancelled = RunInfo(run_id="r-cancelled", date_iso="2024-02-01", date_label="2024-02-01", status="cancelled")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[failed, cancelled]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r-cancelled"

    def test_latest_all_failed_still_renders_newest(self, tmp_path):
        # If every run failed there's nothing trustworthy, but the dashboard
        # must still render something rather than error — pick the newest.
        failed1 = RunInfo(run_id="r2", date_iso="2024-03-01", date_label="2024-03-01", status="failed")
        failed2 = RunInfo(run_id="r1", date_iso="2024-02-01", date_label="2024-02-01", status="failed")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[failed1, failed2]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "latest")
        assert result["selectedRun"]["runId"] == "r2"

    def test_explicit_run_selection_overrides_latest_default(self, tmp_path):
        # Explicit selection by run_id navigates to that run regardless of
        # state — users can still inspect partial runs from the bar chart.
        cancelled = RunInfo(run_id="r-cancelled", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
        complete = RunInfo(run_id="r-complete", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=[cancelled, complete]),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj", "r-cancelled")
        assert result["selectedRun"]["runId"] == "r-cancelled"

    def test_history_path_reads_scalars_not_full_data(self, tmp_path, monkeypatch):
        # Trend-cache perf fix: the HISTORY trend/previous/stale path must read
        # per-run SCALARS (read_run_scalars), NOT full run data (violations,
        # multi-MB). Reading + rescoring full data for every history run was the
        # ~2s cost this fix removes. The selected run still reads full data
        # (its findings are always needed) via dashboard.read_run_data.
        monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
        runs = [
            RunInfo(run_id=f"r{i}", date_iso=f"2024-{i:02d}-01", date_label=f"2024-{i:02d}-01", status="complete")
            for i in range(1, 6)
        ]
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        # The history fetcher goes through read_run_scalars. For these tmp runs
        # (no events.jsonl / evaluation.db) the scalar reader falls back to
        # read_run_data at the runs-module level -- a distinct seam from the
        # dashboard-scope read_run_data used for the SELECTED run. Tracking the
        # two seams separately proves history never uses the full-data
        # dashboard fetcher.
        history_reads: list[str] = []
        selected_full_reads: list[str] = []

        def tracked_history(_root, _project, run_id):
            history_reads.append(run_id)
            return dims

        def tracked_selected(_root, _project, run_id):
            selected_full_reads.append(run_id)
            return dims

        from quodeq.services.dashboard import clear_shared_dimension_cache
        clear_shared_dimension_cache()

        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services.dashboard.read_run_data", side_effect=tracked_selected),
            patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=tracked_history),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            build_dashboard(str(tmp_path), "proj-shared", "r3")

        # History runs are read via the scalar reader (which fell back to the
        # runs-module read_run_data for these no-db tmp runs).
        assert history_reads, "expected history path to use the scalar reader"
        # The selected run's full data is read via the dashboard fetcher; the
        # history path must NOT touch that full-data seam.
        assert selected_full_reads == ["r3"], (
            f"selected run must read full data once via dashboard fetcher; "
            f"got {selected_full_reads}"
        )

    def test_does_not_crash_when_cancelled_runs_precede_selected(self, tmp_path):
        # Regression: build_dashboard formerly raised IndexError when the
        # selected complete run had cancelled/failed runs above it in the
        # full list, because ctx.index (full-list index) was passed to
        # collect_stale_dimensions / _collect_previous_scores along with
        # `history_runs` (filtered list of scoreable runs only). When
        # ctx.index >= len(history_runs), `history_runs[newer_idx]` blew up.
        cancelled_top = [
            RunInfo(run_id=f"c{i}", date_iso="2024-03-01", date_label="2024-03-01", status="cancelled")
            for i in range(5)
        ]
        selected = RunInfo(run_id="r-selected", date_iso="2024-02-15", date_label="2024-02-15", status="complete")
        complete_below = [
            RunInfo(run_id=f"c-below-{i}", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
            for i in range(2)
        ]
        runs = cancelled_top + [selected] + complete_below
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services.dashboard.read_run_data", return_value=dims),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            # Must not raise.
            result = build_dashboard(str(tmp_path), "proj", "r-selected")
        assert result["selectedRun"]["runId"] == "r-selected"
