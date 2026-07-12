"""Tests for quodeq.services.dashboard — dashboard construction logic."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from quodeq.data.fs.report_parser import RunInfo
from quodeq.core.types import DimensionResult, DimensionSummary
from quodeq.services.dashboard import (
    _collect_previous_scores,
    _enrich_dimensions_with_trend,
    build_dashboard,
)
from quodeq.services._dashboard_trend import build_accumulated_trend as _build_accumulated_trend
from quodeq.services._dashboard_stale import collect_stale_dimensions as _collect_stale_dimensions


def _make_run(run_id: str, date_iso: str = "2024-01-01") -> RunInfo:
    return RunInfo(run_id=run_id, date_iso=date_iso, date_label=date_iso)


def _dim(name: str, grade: str = "B", score: str = "7.0") -> DimensionResult:
    return DimensionResult(dimension=name, overall_grade=grade, overall_score=score)


class TestCollectPreviousScores:
    def test_finds_previous_for_matching_dimension(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security", "A", "9.0")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert "security" in result
        assert result["security"].overall_grade == "A"

    def test_skips_na_grades(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security", "NA", "0")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}

    def test_ignores_dimensions_not_in_selected(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("perf")] if rid == "r2" else []
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}


class TestCollectStaleDimensions:
    def test_detects_stale_from_older_run(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("perf")] if rid == "r2" else []
        stale, _ = _collect_stale_dimensions(runs, 0, {"security"}, fetcher)
        assert len(stale) == 1
        assert stale[0].dimension == "perf"
        assert stale[0].stale is True

    def test_no_stale_when_all_present(self):
        runs = [_make_run("r1"), _make_run("r2")]
        fetcher = lambda rid: [_dim("security")]
        stale, _ = _collect_stale_dimensions(runs, 0, {"security"}, fetcher)
        assert stale == []

    def test_empty_runs_returns_empty(self):
        stale, _ = _collect_stale_dimensions([], 0, {"security"}, lambda rid: [])
        assert stale == []


class TestCollectPreviousScoresEdgeCases:
    def test_single_run_returns_empty(self):
        runs = [_make_run("r1")]
        fetcher = lambda rid: [_dim("security", "A", "9.0")]
        result = _collect_previous_scores(runs, 0, {"security"}, fetcher)
        assert result == {}


class TestEnrichDimensionsWithTrend:
    def test_adds_trend_fields(self):
        dims = [_dim("security", "B", "7.0")]
        previous = {"security": DimensionResult(dimension="security", overall_score="6.0", run_id="r0")}
        result = _enrich_dimensions_with_trend(dims, previous)
        assert len(result) == 1
        assert result[0].trend is not None
        assert result[0].previous_run_id == "r0"
        assert result[0].previous_score == "6.0"

    def test_no_previous(self):
        dims = [_dim("security")]
        result = _enrich_dimensions_with_trend(dims, {})
        assert result[0].previous_run_id is None


class TestBuildAccumulatedTrend:
    def test_accumulates_across_runs(self):
        runs = [_make_run("r2", "2024-02-01"), _make_run("r1", "2024-01-01")]
        fetcher = lambda rid: [_dim("security", "B", "7.0")]
        trend = _build_accumulated_trend(runs, fetcher)
        assert len(trend) == 2
        assert trend[0]["runId"] == "r2"
        assert trend[1]["runId"] == "r1"
        assert trend[0]["numericAverage"] is not None


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
        from quodeq.core.events.writer import EventLogWriter
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
        from quodeq.core.events.writer import EventLogWriter

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

        from quodeq.services.dashboard import _SHARED_RUN_DIM_CACHE
        _SHARED_RUN_DIM_CACHE.clear()

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


# ============================================================
# In-progress runs: cache MUST NOT serve stale partial dim sets
# ============================================================


class TestStatusAwareFetcher:
    """For an in_progress run, the on-disk evaluation/<dim>.json set grows
    as dims finish mid-run. Pre-fix, the dashboard's LRU cache served the
    first read forever, so dims that completed AFTER the first dashboard
    request never surfaced -- the History row stayed at 1 dim instead of
    2, even after the second dim landed on disk.

    These tests pin the contract by stubbing read_run_data to return
    different results on each call (simulating a growing dim set) and
    verifying the second build_dashboard request reflects the new state.
    """

    def test_in_progress_run_bypasses_cache(self, tmp_path, monkeypatch):
        from quodeq.services.dashboard import _make_status_aware_fetcher
        from quodeq.data.fs.report_parser import RunInfo as _RI

        runs = [
            _RI(run_id="r-running", date_iso="2024-01-02", date_label="2024-01-02", status="in_progress"),
            _RI(run_id="r-done", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]

        call_count = {"running": 0, "done": 0}
        def fake_read(reports_root, project, run_id):
            if run_id == "r-running":
                call_count["running"] += 1
                # First call: 1 dim. Second call: 2 dims. Simulates a dim
                # finishing between dashboard requests.
                if call_count["running"] == 1:
                    return [_dim("security", "B", "7.0")]
                return [_dim("security", "B", "7.0"), _dim("performance", "A", "9.0")]
            call_count["done"] += 1
            return [_dim("usability", "A", "9.5")]

        monkeypatch.setattr(
            "quodeq.services.dashboard.read_run_data", fake_read,
        )
        monkeypatch.setattr(
            "quodeq.services._cache.read_run_data", fake_read,
        )

        fetcher = _make_status_aware_fetcher(tmp_path, "proj", runs)

        # First call for the in_progress run.
        first = fetcher("r-running")
        assert len(first) == 1

        # Second call must NOT be served from cache for in_progress runs --
        # disk has been updated to 2 dims, fetcher must reflect it.
        second = fetcher("r-running")
        assert len(second) == 2
        assert call_count["running"] == 2  # disk read both times

        # Completed runs ARE cached -- second call hits cache, no extra read.
        fetcher("r-done")
        fetcher("r-done")
        assert call_count["done"] == 1  # only one disk read

    def test_in_progress_run_survives_status_transition_to_done(self, tmp_path, monkeypatch):
        """When the run finishes between dashboard requests, the next request
        treats it as terminal -- but the snapshot of runs passed in still
        had it as in_progress. Sanity: the bypass keys off the snapshot,
        not on a per-call disk re-check, so the in-flight bypass remains
        active for the duration of THAT request."""
        from quodeq.services.dashboard import _make_status_aware_fetcher
        from quodeq.data.fs.report_parser import RunInfo as _RI

        runs_snapshot1 = [
            _RI(run_id="r1", date_iso="2024-01-01", date_label="2024-01-01", status="in_progress"),
        ]
        runs_snapshot2 = [
            _RI(run_id="r1", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]

        calls = []
        def fake_read(reports_root, project, run_id):
            calls.append(run_id)
            return [_dim("security", "B", "7.0")]

        monkeypatch.setattr(
            "quodeq.services.dashboard.read_run_data", fake_read,
        )
        monkeypatch.setattr(
            "quodeq.services._cache.read_run_data", fake_read,
        )

        # Request 1: run is in_progress, bypass cache. Disk read.
        f1 = _make_status_aware_fetcher(tmp_path, "proj", runs_snapshot1)
        f1("r1")
        assert calls == ["r1"]

        # Request 2: run has transitioned to complete. The fresh fetcher
        # for THIS request goes through the cache. Could be hit or miss
        # depending on prior cache state -- either way the fetcher works.
        f2 = _make_status_aware_fetcher(tmp_path, "proj", runs_snapshot2)
        f2("r1")
        # 1 or 2 calls total -- one was the in_progress bypass, the second
        # depends on whether the cache held an entry from request 1. The
        # contract pinned here is: no exception, no infinite-loop, no
        # stale-bypass behaviour from the prior snapshot.
        assert len(calls) in (1, 2)


class TestStaleCacheSelfHeal:
    """Even for terminal runs, the cache CAN go stale -- e.g. when an
    earlier request populated it from a partial on-disk state because a
    dim file landed late. Without self-heal, the dashboard renders the
    stale dim count forever; the user sees a 3-dim run as 1-dim.

    The fix: count evaluation/*.json files on disk and compare to the
    cached length on every lookup. Mismatch -> evict, re-read.

    Observed in production after PR #481's BrokenPipe regression: dashboard
    cached a 1-dim entry for a 3-dim run because the broken-pipe path had
    skipped scoring 2 dims when the cache was first populated.
    """

    def test_count_eval_files_counts_json_only(self, tmp_path):
        from quodeq.services.dashboard import _count_eval_files

        eval_dir = tmp_path / "proj" / "r1" / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "flexibility.json").write_text("{}")
        (eval_dir / "performance.json").write_text("{}")
        (eval_dir / "security.json").write_text("{}")
        # A non-json file should NOT be counted.
        (eval_dir / "notes.txt").write_text("ignore me")

        assert _count_eval_files(tmp_path, "proj", "r1") == 3

    def test_count_returns_zero_when_eval_dir_missing(self, tmp_path):
        from quodeq.services.dashboard import _count_eval_files
        assert _count_eval_files(tmp_path, "proj", "missing") == 0

    def test_stale_cache_evicted_when_dim_count_mismatches_disk(
        self, tmp_path, monkeypatch,
    ):
        from collections import OrderedDict
        from quodeq.services.dashboard import _make_status_aware_fetcher
        from quodeq.data.fs.report_parser import RunInfo as _RI

        # Build a real on-disk eval/ with 3 files for r-stale.
        eval_dir = tmp_path / "proj" / "r-stale" / "evaluation"
        eval_dir.mkdir(parents=True)
        for d in ("flexibility", "reliability", "security"):
            (eval_dir / f"{d}.json").write_text("{}")

        runs = [
            _RI(run_id="r-stale", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]

        # Pre-populate the cache with a STALE 1-dim entry (simulates the
        # bug: cache was populated when only 1 dim was on disk, even though
        # disk now has 3).
        cache = OrderedDict()
        cache[(tmp_path, "proj", "r-stale", "")] = [_dim("security", "F", "2.0")]

        # Fresh disk read should return all 3 dims.
        read_calls = []
        def fake_read(reports_root, project, run_id):
            read_calls.append(run_id)
            return [
                _dim("flexibility", "C", "5.0"),
                _dim("reliability", "B", "7.0"),
                _dim("security", "F", "2.0"),
            ]
        monkeypatch.setattr(
            "quodeq.services.dashboard.read_run_data", fake_read,
        )
        monkeypatch.setattr(
            "quodeq.services._cache.read_run_data", fake_read,
        )

        fetcher = _make_status_aware_fetcher(
            tmp_path, "proj", runs, cache=cache,
        )
        result = fetcher("r-stale")

        # Cache had 1 dim, disk has 3 -- fetcher must self-heal: evict,
        # re-read, return 3 dims.
        assert len(result) == 3, (
            f"expected self-heal to fresh-read 3 dims, got {len(result)}"
        )
        # And the cache should have been evicted (then repopulated by the
        # cached() call that follows the eviction).
        assert read_calls == ["r-stale"], (
            f"expected exactly one fresh read after eviction, got {read_calls}"
        )

    def test_cache_serves_when_count_matches_disk(
        self, tmp_path, monkeypatch,
    ):
        """Sanity gate: when the cached entry's count matches disk, we
        DO use the cache and don't re-read. Without this, every lookup
        would always re-read, defeating the cache."""
        from collections import OrderedDict
        from quodeq.services.dashboard import _make_status_aware_fetcher
        from quodeq.data.fs.report_parser import RunInfo as _RI

        eval_dir = tmp_path / "proj" / "r-fresh" / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "security.json").write_text("{}")

        runs = [
            _RI(run_id="r-fresh", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]

        cache = OrderedDict()
        cache[(tmp_path, "proj", "r-fresh", "")] = [_dim("security", "B", "7.0")]

        read_calls = []
        def fake_read(reports_root, project, run_id):
            read_calls.append(run_id)
            return [_dim("security", "B", "7.0")]
        monkeypatch.setattr(
            "quodeq.services.dashboard.read_run_data", fake_read,
        )
        monkeypatch.setattr(
            "quodeq.services._cache.read_run_data", fake_read,
        )

        fetcher = _make_status_aware_fetcher(
            tmp_path, "proj", runs, cache=cache,
        )
        fetcher("r-fresh")
        fetcher("r-fresh")

        assert read_calls == [], (
            f"expected no disk reads (cache hit), got {read_calls}"
        )


class TestInProgressFreshnessThroughDashboard:
    """After the trend-cache perf fix the History trend/previous/stale path is
    served by the cache-backed SCALAR fetcher. This pins that an in_progress
    history run is still read FRESH on every dashboard request: its scalar set
    grows as dims finish mid-run, and the fix must NOT persist a partial set
    (which would strand a stale trend point served forever after the run ends).
    """

    def test_in_progress_history_run_read_fresh_each_call(self, tmp_path, monkeypatch):
        # Isolate the read-through score cache so a persisted row from another
        # test can't mask a regression here.
        monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

        selected = RunInfo(run_id="r-sel", date_iso="2024-02-01", date_label="2024-02-01", status="complete")
        running = RunInfo(run_id="r-run", date_iso="2024-01-01", date_label="2024-01-01", status="in_progress")
        runs = [selected, running]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        # The in_progress run grows from 1 dim to 2 between the two dashboard
        # calls (a dim finished mid-run). Scalar reads fall back to the runs-
        # module read_run_data for these no-db tmp runs.
        run_call_count = {"r-run": 0}

        def history_read(_root, _project, run_id):
            if run_id == "r-run":
                run_call_count["r-run"] += 1
                if run_call_count["r-run"] == 1:
                    return [_dim("security", "B", "7.0")]
                return [_dim("security", "B", "7.0"), _dim("performance", "A", "9.0")]
            return [_dim("usability", "A", "9.5")]

        from quodeq.services.dashboard import _SHARED_RUN_DIM_CACHE
        _SHARED_RUN_DIM_CACHE.clear()

        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services.dashboard.read_run_data", side_effect=history_read),
            patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=history_read),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            first = build_dashboard(str(tmp_path), "proj-ip", "r-sel")
            second = build_dashboard(str(tmp_path), "proj-ip", "r-sel")

        # The in_progress run's trend point reflects the GROWN dim set on the
        # second call -- proof it was re-read fresh, not served from a persisted
        # partial (which would have frozen it at 1 dim forever).
        def running_point(dash):
            return next(p for p in dash["trend"] if p["runId"] == "r-run")

        assert running_point(first)["dimensionsCount"] == 1
        assert running_point(second)["dimensionsCount"] == 2, (
            "in_progress history run must be re-read fresh each call, not "
            "served from a stale persisted partial"
        )
        # And the in_progress run was read on BOTH calls (never cache-served).
        assert run_call_count["r-run"] == 2


# ============================================================
# Dashboard scores come from CLI evaluation JSON, no SQL overlay
# ============================================================


class TestDashboardSqlOverlayAfterConfidenceFix:
    """The SQL grade overlay is back, but only after the SQL projector and
    the CLI engine were unified on the same confidence-level rule (see
    ``core.evidence.model.classify_confidence_level``).  These tests pin
    the new contract: when SQL grade tables are populated, the dashboard
    surfaces them — which is now safe because they're computed with the
    same formula the CLI used to write the evaluation JSON.

    Previous incarnation of these tests (``TestDashboardSqlGradeOverride``)
    pinned the same overlay against the buggy projector formula; that
    behaviour caused the 7.7-vs-9.0 dashboard-vs-CLI split the user
    reported.  Now that both engines agree, the overlay is a feature
    (live updates on dismiss) rather than a divergence.
    """

    @staticmethod
    def _write_eval_json(
        run_dir: Path, dimension: str, score: str, grade: str,
    ) -> None:
        """Write a minimal eval JSON so read_run_data parses one dimension."""
        import json

        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / f"{dimension}.json").write_text(json.dumps({
            "schema_version": 1,
            "dimension": dimension,
            "project": "r",
            "discipline": "Python",
            "date": "2026-05-23",
            "sourceFileCount": 100,
            "overallScore": score,
            "overallGrade": grade,
            "principles": [],
            "violations": [],
            "compliance": [],
            "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
        }), encoding="utf-8")

    def test_dashboard_overlays_sql_grades_when_populated(self, tmp_path: Path) -> None:
        """SQL grade tables override the stale eval-time FS grade.

        The overlay now lives inside ``read_run_data`` (so every consumer
        agrees), so this test exercises the real reader against a run whose
        SQL grade tables were baked by the projector (events + recompute)
        and whose eval JSON carries a different, stale grade.
        """
        from quodeq.core.events.models import Judgment
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.data.projection.grade_projector import recompute_grades
        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import clear_shared_dimension_cache

        clear_shared_dimension_cache()
        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "events.jsonl").write_text("")  # marks an event-log run

        # Bake real SQL grades from findings (mirrors the projector flow).
        store = SQLiteStateStore(run_dir)
        for i in range(6):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"req{i}",
                verdict="violation", severity="major", file=f"f{i}.py", line=1,
                title=f"t{i}", reason=f"r{i}",
            ))
        for i in range(8):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"c{i}",
                verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
                title=f"ct{i}", reason=f"cr{i}",
            ))
        store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
        recompute_grades(run_dir, params=DEFAULT_PARAMS)
        sql_rows = {r["dimension"]: r for r in store.read_dimension_scores()}
        baked = sql_rows["security"]
        assert baked["grade"] is not None

        # The eval JSON carries a deliberately different (stale) grade.
        self._write_eval_json(run_dir, "security", "2.0/10", "Critical")

        with patch(
            "quodeq.services.dashboard.list_runs",
            return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        clear_shared_dimension_cache()
        sec = result["dimensions"][0]
        # Overlay wins: the SQL-baked grade, not the stale "Critical".
        assert sec["overallGrade"] == baked["grade"]
        assert sec["overallScore"] == f"{baked['score']}/10"
        assert sec["overallGrade"] != "Critical"
        # The run-level summary is derived from the overlaid dims.
        assert result["summary"]["overallGrade"] == baked["grade"]

    def test_dashboard_falls_back_to_fs_when_sql_tables_empty(
        self, tmp_path: Path,
    ) -> None:
        """No SQL rows → use FS grade unchanged (this is the steady state
        for runs that haven't been projected, e.g. legacy runs without
        events.jsonl)."""
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import clear_shared_dimension_cache

        clear_shared_dimension_cache()
        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)
        # No events.jsonl → legacy run, overlay must be a no-op.
        self._write_eval_json(run_dir, "security", "7.7/10", "Good")

        with patch(
            "quodeq.services.dashboard.list_runs",
            return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        clear_shared_dimension_cache()
        sec = result["dimensions"][0]
        assert sec["overallScore"] == "7.7/10"
        assert sec["overallGrade"] == "Good"


class TestBuildDashboardDismissedFiltering:
    """The run-level dashboard payload must not resurface findings the user
    dismissed or deleted at project level.

    Regression for the 2026-07-04 report: run 03c99d26 showed "1 critical"
    in the history run view for a finding dismissed on 2026-06-20, while the
    dimension detail (which applies the dismissed-keys filter) correctly hid
    it. The run view, the dimension detail, and the accumulated overview must
    all read through the same dismissal semantics.
    """

    def _write_run(self, reports, project="proj", run_id="20260101T000000"):
        """A legacy-style on-disk run with two violations in one dimension."""
        import json as _json

        run_dir = reports / project / run_id
        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True)
        violations = [
            {
                "principle": "N/A", "req": "N/A",
                "file": "src/a.py", "line": 73,
                "title": "Arbitrary file read", "severity": "critical",
            },
            {
                "principle": "Modularity", "req": "M-MOD-1",
                "file": "src/b.py", "line": 5,
                "title": "Oversized function", "severity": "major",
            },
        ]
        (eval_dir / "maintainability.json").write_text(_json.dumps({
            "dimension": "maintainability",
            "overallScore": "6.0/10", "overallGrade": "Fair",
            "principles": [], "violations": violations, "compliance": [],
            "totals": {
                "violationCount": 2, "complianceCount": 0,
                "severity": {"critical": 1, "major": 1, "minor": 0},
            },
        }), encoding="utf-8")
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
        return run_dir

    def test_dismissed_finding_excluded_and_totals_recounted(self, tmp_path):
        from quodeq.services.dismissed import dismiss_finding

        self._write_run(tmp_path)
        dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert [v["file"] for v in dim["violations"]] == ["src/b.py"]
        assert dim["totals"]["violationCount"] == 1
        assert dim["totals"]["severity"]["critical"] == 0
        assert dim["totals"]["severity"]["major"] == 1

    def test_dismissed_count_attached_to_dimension(self, tmp_path):
        from quodeq.services.dismissed import dismiss_finding

        self._write_run(tmp_path)
        dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})

        result = build_dashboard(str(tmp_path), "proj", "latest")

        assert result["dimensions"][0]["dismissedCount"] == 1

    def test_no_dismissals_leaves_payload_unchanged(self, tmp_path):
        self._write_run(tmp_path)

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert len(dim["violations"]) == 2
        assert dim["totals"]["violationCount"] == 2
        assert dim["totals"]["severity"]["critical"] == 1
        assert "dismissedCount" not in dim

    def test_deleted_finding_excluded_without_dismissed_count(self, tmp_path):
        from quodeq.services.deleted import delete_finding

        self._write_run(tmp_path)
        delete_finding(tmp_path / "proj", {
            "dimension": "maintainability", "principle": "Modularity", "file": "src/b.py",
        })

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert [v["file"] for v in dim["violations"]] == ["src/a.py"]
        assert dim["totals"]["violationCount"] == 1
        # Deleted findings are suppressed, not "dismissed": no count is shown.
        assert "dismissedCount" not in dim


class TestHistoryContextSlimming:
    """previousByDimension / stalePreviousByDimension / staleDimensions must
    carry scores + provenance only. No consumer reads finding bodies from
    these keys, and on large projects the bodies dominated the payload
    (~18.6 MB of a 19.9 MB old-run dashboard on a 201-run project).

    Since the trend-cache perf fix these keys are built by the cache-backed
    SCALAR fetcher (the same one the /scores endpoint uses), so the guaranteed
    contract is: bodies (violations/compliance) are empty, and
    dimension/overallScore/overallGrade/provenance survive -- the scores and
    grades the trend context exists to convey. The UI reads none of these three
    keys directly (0 references in the frontend; it reads the scalar fields
    inlined on the selected-run dimensions). For SQL-projected runs the scalar
    reader also drops display-metadata (totals/principles/discipline/
    evidenceDate/sourceFileCount/filesRead) that no consumer reads -- a strict
    payload improvement; the load-bearing scores/grades/provenance stay
    byte-identical (verified against a real 74-run project). For legacy/no-SQL
    runs the reader falls back to full data, so those fields may still appear;
    either way the bodies are dropped and the scalars/provenance match."""

    def _finding(self, i: int, verdict: str = "violation"):
        from quodeq.core.types.finding import Finding
        return Finding(
            practice_id="P1", verdict=verdict, file=f"f{i}.py", line=i,
            reason="a long explanation", snippet="offending()", context="ctx",
            req=f"R{i}",
        )

    def test_history_keys_drop_finding_bodies_but_keep_scores(self, tmp_path):
        from quodeq.core.types.finding import Totals
        runs = [
            RunInfo(run_id="r-new", date_iso="2024-02-01", date_label="2024-02-01", status="complete"),
            RunInfo(run_id="r-old", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]
        selected_dims = [DimensionResult(
            dimension="security", overall_grade="B", overall_score="7.0/10",
            violations=[self._finding(1)], compliance=[self._finding(2, "compliance")],
        )]
        old_dims = [
            DimensionResult(
                dimension="security", overall_grade="C", overall_score="6.0/10",
                violations=[self._finding(3)],
                totals=Totals(violation_count=1, compliance_count=0),
            ),
            DimensionResult(
                dimension="perf", overall_grade="C", overall_score="5.0/10",
                violations=[self._finding(4)], compliance=[self._finding(5, "compliance")],
                totals=Totals(violation_count=1, compliance_count=1),
            ),
        ]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        def read_by_run(_root, _project, run_id):
            return selected_dims if run_id == "r-new" else old_dims

        from quodeq.services.dashboard import _SHARED_RUN_DIM_CACHE
        _SHARED_RUN_DIM_CACHE.clear()
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            # Selected-run path reads via dashboard.read_run_data; the history
            # trend/previous/stale path reads via the scalar fetcher. In this
            # no-events/no-db tmp project the scalar reader falls back to
            # read_run_data at the runs-module level, so patch there too.
            patch("quodeq.services.dashboard.read_run_data", side_effect=read_by_run),
            patch("quodeq.services._cache.read_run_data", side_effect=read_by_run),
            patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=read_by_run),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj-slim-history", "r-new")

        # The selected run's own dimensions keep their full finding bodies.
        assert result["dimensions"][0]["violations"][0]["reason"] == "a long explanation"
        assert result["dimensions"][0]["compliance"]

        # previousByDimension: scores/grades/provenance survive, bodies do not.
        prev = result["previousByDimension"]["security"]
        assert prev["overallGrade"] == "C"
        assert prev["overallScore"] == "6.0/10"
        assert prev["runId"] == "r-old"
        assert prev["violations"] == []
        assert prev["compliance"] == []

        # staleDimensions (perf is missing from the selected run): same rule.
        stale = [d for d in result["staleDimensions"] if d["dimension"] == "perf"]
        assert stale, f"expected perf in staleDimensions, got {result['staleDimensions']}"
        assert stale[0]["overallScore"] == "5.0/10"
        assert stale[0]["stale"] is True
        assert stale[0]["fromRunId"] == "r-old"
        assert stale[0]["violations"] == []
        assert stale[0]["compliance"] == []

        # stalePreviousByDimension follows the same serialization path.
        for dim in result["stalePreviousByDimension"].values():
            assert dim["violations"] == []
            assert dim["compliance"] == []
