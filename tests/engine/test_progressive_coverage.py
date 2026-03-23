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
