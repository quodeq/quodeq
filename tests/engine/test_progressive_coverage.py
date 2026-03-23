"""Integration tests for progressive coverage (backfill) in incremental mode."""
from __future__ import annotations

from quodeq.analysis.incremental import identify_backfill_files


class TestIdentifyBackfillFiles:
    def test_new_project_all_files_are_backfill(self):
        all_files = [f"file{i}.py" for i in range(100)]
        result = identify_backfill_files(all_files, [], set())
        assert len(result) == 100

    def test_partially_covered_project(self):
        all_files = [f"file{i}.py" for i in range(100)]
        prev = [f"file{i}.py" for i in range(50)]
        result = identify_backfill_files(all_files, prev, set())
        assert len(result) == 50
        assert all(f not in prev for f in result)

    def test_changed_files_excluded_from_backfill(self):
        all_files = ["a.py", "b.py", "c.py"]
        prev = ["a.py"]
        changed = {"b.py"}
        result = identify_backfill_files(all_files, prev, changed)
        assert result == ["c.py"]

    def test_fully_covered_returns_empty(self):
        all_files = ["a.py", "b.py"]
        result = identify_backfill_files(all_files, ["a.py", "b.py"], set())
        assert result == []


class TestAnalyzedFilesAccumulation:
    def test_accumulate_across_three_runs(self):
        """Simulate 3 runs: each covers more files."""
        all_files = [f"f{i}.py" for i in range(10)]

        # Run 1: covers f0-f3
        run1_analyzed = {"f0.py", "f1.py", "f2.py", "f3.py"}
        backfill = identify_backfill_files(all_files, list(run1_analyzed), set())
        assert len(backfill) == 6  # f4-f9

        # Run 2: covers f4-f6 (3 more)
        run2_new = {"f4.py", "f5.py", "f6.py"}
        run2_analyzed = run1_analyzed | run2_new
        backfill = identify_backfill_files(all_files, list(run2_analyzed), set())
        assert len(backfill) == 3  # f7-f9

        # Run 3: covers f7-f9 (last 3)
        run3_new = {"f7.py", "f8.py", "f9.py"}
        run3_analyzed = run2_analyzed | run3_new
        backfill = identify_backfill_files(all_files, list(run3_analyzed), set())
        assert len(backfill) == 0  # fully covered

    def test_deleted_files_excluded_from_accumulation(self):
        """Files removed from project should not persist in analyzed set."""
        all_files = ["a.py", "b.py"]  # c.py was deleted
        prev_analyzed = ["a.py", "b.py", "c.py"]
        # Intersection with current files removes c.py
        accumulated = set(prev_analyzed) & set(all_files)
        assert accumulated == {"a.py", "b.py"}
