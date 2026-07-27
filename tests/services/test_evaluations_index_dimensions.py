"""Dimension recovery for index-served run snapshots.

"All dimensions" runs record `dimensions: []` in status.json (the raw,
unresolved CLI filter is None). The UI's live findings feed fetches per-dim
evals from `job.dimensions`, so an empty list left the feed permanently blank
and the finished-run strip showing VIOLATIONS 0 for every full scan served
via the index. scan_progress already recovers the resolved list from the
per-dim sidecars; the index snapshot path must do the same.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._evaluations_index import _read_dimensions_from_status


def _write_status(run_dir: Path, dimensions: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(
        json.dumps({"schema_version": 1, "state": "running", "dimensions": dimensions}),
        encoding="utf-8",
    )


class TestReadDimensionsFromStatus:
    def test_explicit_dimensions_returned_as_is(self, tmp_path: Path) -> None:
        _write_status(tmp_path, ["security"])
        assert _read_dimensions_from_status(tmp_path) == ["security"]

    def test_empty_dimensions_recovered_from_dimensions_json(self, tmp_path: Path) -> None:
        _write_status(tmp_path, [])
        (tmp_path / "dimensions.json").write_text(
            json.dumps({
                "schema_version": 1,
                "dimensions": {"security": {"state": "done"}, "reliability": {"state": "running"}},
            }),
            encoding="utf-8",
        )
        assert _read_dimensions_from_status(tmp_path) == ["security", "reliability"]

    def test_empty_dimensions_recovered_from_dim_estimates(self, tmp_path: Path) -> None:
        _write_status(tmp_path, [])
        (tmp_path / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 10, "reason": "incremental"}}),
            encoding="utf-8",
        )
        assert _read_dimensions_from_status(tmp_path) == ["security"]

    def test_empty_dimensions_no_sidecars_stays_empty(self, tmp_path: Path) -> None:
        _write_status(tmp_path, [])
        assert _read_dimensions_from_status(tmp_path) == []


class TestReadTimeLimitFromStatus:
    def test_reads_time_limit(self, tmp_path: Path) -> None:
        from quodeq.services._evaluations_index import _read_time_limit_from_status
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "status.json").write_text(
            json.dumps({"schema_version": 1, "state": "running", "time_limit_s": 900}),
            encoding="utf-8",
        )
        assert _read_time_limit_from_status(tmp_path) == 900

    def test_missing_field_returns_none(self, tmp_path: Path) -> None:
        from quodeq.services._evaluations_index import _read_time_limit_from_status
        _write_status(tmp_path, [])
        assert _read_time_limit_from_status(tmp_path) is None
