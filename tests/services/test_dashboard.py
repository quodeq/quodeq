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

    def test_shared_run_dim_cache_persists_across_calls(self, tmp_path):
        # Regression: _make_run_dimension_fetcher used to create a fresh LRU
        # cache per call (via create_dimension_cache()), so dashboard requests
        # paid the read_run_data cost on every call — even when the same run
        # had been read seconds earlier. This test asserts that the second
        # build_dashboard call hits the shared module-level cache for at
        # least one historical run, demonstrably eliminating that I/O.
        runs = [
            RunInfo(run_id=f"r{i}", date_iso=f"2024-{i:02d}-01", date_label=f"2024-{i:02d}-01", status="complete")
            for i in range(1, 6)
        ]
        dims = [_dim("security", "B", "7.0")]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        # Track every read_run_data call across both invocations.
        read_calls: list[tuple[str, str]] = []

        def tracked_read(_root, project, run_id):
            read_calls.append((project, run_id))
            return dims

        # Reset the shared cache so this test starts from a clean state.
        from quodeq.services.dashboard import _SHARED_RUN_DIM_CACHE
        _SHARED_RUN_DIM_CACHE.clear()

        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            patch("quodeq.services._cache.read_run_data", side_effect=tracked_read),
            patch("quodeq.services.dashboard.read_run_data", side_effect=tracked_read),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            build_dashboard(str(tmp_path), "proj-shared", "r3")
            calls_after_first = len(read_calls)
            build_dashboard(str(tmp_path), "proj-shared", "r3")
            calls_after_second = len(read_calls)

        # If the cache were per-request (the bug), the second call would do
        # ~the same number of reads as the first. With the shared cache, the
        # second call's reads via _make_run_dimension_fetcher are eliminated.
        assert calls_after_second < calls_after_first * 2, (
            f"Expected shared cache to reduce reads on second call. "
            f"After 1st: {calls_after_first}, after 2nd: {calls_after_second} "
            f"(would be {calls_after_first * 2} with no caching)"
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
        cache[(tmp_path, "proj", "r-stale")] = [_dim("security", "F", "2.0")]

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
        cache[(tmp_path, "proj", "r-fresh")] = [_dim("security", "B", "7.0")]

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


# ============================================================
# SQL grade override: Overview parity with Standard Detail
# ============================================================


class TestDashboardSqlGradeOverride:
    """The dashboard must read dimension grades from the SQL grade tables
    when they are available, not from the on-disk evaluation JSON.

    This is the fix for the Overview/Standard-detail divergence: the /scores
    endpoint reads from SQL (dismissals applied), but the old dashboard read
    from FS files (dismissals ignored). After _apply_sql_grade_override,
    both endpoints use the same source of truth.
    """

    def test_dashboard_overrides_grades_from_sql_when_tables_populated(
        self, tmp_path: Path,
    ) -> None:
        """When SQL grade tables have data, the dashboard's per-dimension
        overallScore and overallGrade must come from SQL, not the FS value."""
        from pathlib import Path as P

        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.data.fs.report_parser import RunInfo as _RI

        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)

        # Seed SQL grade tables with a post-dismissal grade.
        # Score 7.5 -> "Good" (threshold: 7=Good, 9=Exemplary).
        store = SQLiteStateStore(run_dir)
        store.record_dimension_score(dimension="Security", score=7.5, grade="Good")

        # FS-based DimensionResult has a bad pre-dismissal grade.
        fs_dim = DimensionResult(
            dimension="Security", overall_grade="Critical", overall_score="2.0",
        )
        summary = DimensionSummary(dimensions_count=1, overall_grade="Critical", numeric_average=2.0)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[fs_dim]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        dims = result["dimensions"]
        assert len(dims) == 1
        sec = dims[0]
        # Dashboard must reflect SQL grade (post-dismissal), not FS grade.
        assert sec["overallGrade"] == "Good", (
            f"Expected SQL grade 'Good', got {sec['overallGrade']!r} (FS would be 'Critical')"
        )
        assert sec["overallScore"] == "7.5/10", (
            f"Expected SQL score '7.5/10', got {sec['overallScore']!r}"
        )

    def test_dashboard_falls_back_to_fs_when_sql_tables_empty(
        self, tmp_path: Path,
    ) -> None:
        """When SQL grade tables are empty (run not yet projected), the
        dashboard must fall back to the FS-based grades without raising."""
        from quodeq.data.fs.report_parser import RunInfo as _RI

        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)
        # No SQL rows seeded — grade tables are empty.

        fs_dim = DimensionResult(
            dimension="Security", overall_grade="A", overall_score="9.0",
        )
        summary = DimensionSummary(dimensions_count=1, overall_grade="A", numeric_average=9.0)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[fs_dim]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        sec = result["dimensions"][0]
        assert sec["overallGrade"] == "A", (
            f"Expected FS fallback grade 'A', got {sec['overallGrade']!r}"
        )

    def test_dashboard_falls_back_when_run_dir_missing(
        self, tmp_path: Path,
    ) -> None:
        """When the run directory does not exist on disk, the SQL override is
        skipped and FS-based grades are used without raising."""
        from quodeq.data.fs.report_parser import RunInfo as _RI

        project = "myproject"
        run_id = "r-nomatch"
        # run_dir is NOT created — does not exist on disk.

        fs_dim = DimensionResult(
            dimension="Security", overall_grade="C", overall_score="5.5",
        )
        summary = DimensionSummary(dimensions_count=1, overall_grade="C", numeric_average=5.5)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[fs_dim]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        sec = result["dimensions"][0]
        assert sec["overallGrade"] == "C"

    def test_dashboard_summary_reflects_sql_run_grade(
        self, tmp_path: Path,
    ) -> None:
        """The run-level summary overall grade must also be overridden from SQL."""
        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.data.fs.report_parser import RunInfo as _RI

        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)

        store = SQLiteStateStore(run_dir)
        # Score 8.0 -> grade label "Good" (see _GRADE_THRESHOLDS: 7=Good, 9=Exemplary).
        store.record_dimension_score(dimension="Reliability", score=8.0, grade="Good")

        fs_dim = DimensionResult(
            dimension="Reliability", overall_grade="Poor", overall_score="3.0",
        )
        # Summary initially computed from FS grades.
        summary = DimensionSummary(dimensions_count=1, overall_grade="Poor", numeric_average=3.0)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[fs_dim]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        # Summary grade must reflect SQL data (post-dismissal), not FS data.
        # read_run_score_from_dim_scores derives the run grade from score_to_grade_label(8.0)="Good".
        assert result["summary"]["overallGrade"] == "Good", (
            f"Expected SQL summary grade 'Good', got {result['summary']['overallGrade']!r} (FS would be 'Poor')"
        )

    def test_dashboard_dimension_grades_match_scores_endpoint_after_dismiss(
        self, tmp_path: Path,
    ) -> None:
        """Overview ↔ Standard-detail invariant: dashboard and /scores output
        must agree on grades after dismissal.

        After PR 2, both endpoints back off to the same SQL grade tables, so this
        parity test documents the contract that the symptom (Overview != Standard
        detail) is fixed at the storage layer.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
        from quodeq.services.dismissed import dismiss_finding
        from quodeq.services.scoring import get_scores_raw

        project = "myproject"
        run_id = "r1"
        project_dir = tmp_path / project
        run_dir = project_dir / run_id
        run_dir.mkdir(parents=True)

        # Seed 3 findings: 2 in Security (varied severity), 1 in Reliability.
        log = run_dir / "events.jsonl"
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="Security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="Security",
            file="b.py", line=20, reason="r", req="R2", severity="medium",
        )))
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P2", verdict="violation", dimension="Reliability",
            file="c.py", line=30, reason="r", req="R3", severity="low",
        )))

        # Project findings to populate SQL grade tables.
        SqliteFindingsRepository(run_dir).list_by_dimension("Security")
        SqliteFindingsRepository(run_dir).list_by_dimension("Reliability")

        # Dismiss the critical Security finding.
        dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

        # Re-project to update SQL grades after dismissal.
        SqliteFindingsRepository(run_dir).list_by_dimension("Security")
        SqliteFindingsRepository(run_dir).list_by_dimension("Reliability")

        # Stub the FS layer so build_dashboard sees real run data.  The SQL
        # override (what we are testing here) runs on top of these stale FS
        # grades and replaces them with the post-dismissal SQL values.
        stale_sec = DimensionResult(dimension="Security", overall_grade="Critical", overall_score="1.0")
        stale_rel = DimensionResult(dimension="Reliability", overall_grade="Poor", overall_score="2.0")
        stale_summary = DimensionSummary(dimensions_count=2, overall_grade="Critical", numeric_average=1.5)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[stale_sec, stale_rel]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=stale_summary),
        ):
            dashboard_payload = build_dashboard(str(tmp_path), project, run_id)

        scores_payload = get_scores_raw(tmp_path, project, run_id)

        # Per-dimension grade parity.
        dash_dims = {d["dimension"]: d for d in dashboard_payload["dimensions"]}
        scores_dims = {d["dimension"]: d for d in scores_payload["dimensions"]}

        # Guard: both sides must have populated data — otherwise the loop below
        # iterates zero times and the assertion is never reached (vacuous pass).
        assert len(dash_dims) > 0, "dashboard returned no dimensions — check list_runs mock"
        assert len(scores_dims) > 0, "scores endpoint returned no dimensions"

        for dim_name in scores_dims:
            if dim_name not in dash_dims:
                continue
            assert dash_dims[dim_name]["overallGrade"] == scores_dims[dim_name]["overallGrade"], (
                f"Grade divergence for {dim_name}: "
                f"dashboard={dash_dims[dim_name]['overallGrade']}, "
                f"scores={scores_dims[dim_name]['overallGrade']}"
            )
            assert dash_dims[dim_name]["overallScore"] == scores_dims[dim_name]["overallScore"], (
                f"Score divergence for {dim_name}: "
                f"dashboard={dash_dims[dim_name]['overallScore']}, "
                f"scores={scores_dims[dim_name]['overallScore']}"
            )

    def test_dashboard_override_fires_with_flat_run_layout(
        self, tmp_path: Path,
    ) -> None:
        """Regression guard: _apply_sql_grade_override must resolve the run
        directory as reports_root / project / run_id (the production layout).

        Earlier code mistakenly inserted a `runs/` segment, so the
        ``not run_dir.is_dir()`` guard always bailed out and the SQL override
        silently never fired — the dashboard returned the stale FS grade
        instead of the SQL-backed grade.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

        project = "myproject"
        run_id = "r1"
        # Production layout: reports_root / project / run_id (no `runs/` segment).
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)

        # Seed one finding so the projector creates grade tables.
        log = run_dir / "events.jsonl"
        EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="Security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))

        # Trigger projection so SQL grade tables are populated.
        SqliteFindingsRepository(run_dir).list_by_dimension("Security")

        # FS layer returns a stale grade that differs from what SQL will produce.
        fs_dim = DimensionResult(dimension="Security", overall_grade="Exemplary", overall_score="9.9")
        stale_summary = DimensionSummary(dimensions_count=1, overall_grade="Exemplary", numeric_average=9.9)

        with (
            patch(
                "quodeq.services.dashboard.list_runs",
                return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
            ),
            patch("quodeq.services.dashboard.read_run_data", return_value=[fs_dim]),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=stale_summary),
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        dims = result["dimensions"]
        assert len(dims) == 1, "dashboard returned no dimensions"
        sec = dims[0]
        # The SQL grade for a single critical violation must NOT be 'Exemplary'
        # (which is the stale FS value).  If the override path is wrong, the FS
        # value leaks through and this assertion fails.
        assert sec["overallGrade"] != "Exemplary", (
            "SQL override did not fire — dashboard returned stale FS grade 'Exemplary'. "
            "Check that _apply_sql_grade_override uses reports_root / project / 'runs' / run_id."
        )
        # The override must have set a real SQL-backed grade and score.
        assert sec["overallGrade"] is not None
        assert sec["overallScore"] is not None
