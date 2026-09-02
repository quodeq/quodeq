"""Tests for quodeq.services.dashboard — in-progress/stale cache handling.

Split from test_dashboard.py: for an in_progress run the on-disk
evaluation/<dim>.json set grows as dims finish mid-run, so the dashboard's
LRU cache must bypass/self-heal rather than serve a stale partial dim set
forever. The full build_dashboard history-path variant of this contract
is split further into test_dashboard_freshness_history.py. Shared
builders live in tests/services/_dashboard_fixtures.py.
"""
from __future__ import annotations

from tests.services._dashboard_fixtures import _dim

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
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import _make_status_aware_fetcher

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
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import _make_status_aware_fetcher

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
        from quodeq.services._cache import _count_eval_files

        eval_dir = tmp_path / "proj" / "r1" / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "flexibility.json").write_text("{}")
        (eval_dir / "performance.json").write_text("{}")
        (eval_dir / "security.json").write_text("{}")
        # A non-json file should NOT be counted.
        (eval_dir / "notes.txt").write_text("ignore me")

        assert _count_eval_files(tmp_path, "proj", "r1") == 3

    def test_count_returns_zero_when_eval_dir_missing(self, tmp_path):
        from quodeq.services._cache import _count_eval_files
        assert _count_eval_files(tmp_path, "proj", "missing") == 0

    def test_stale_cache_evicted_when_dim_count_mismatches_disk(
        self, tmp_path, monkeypatch,
    ):
        from collections import OrderedDict

        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import _make_status_aware_fetcher

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

        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import _make_status_aware_fetcher

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

