"""Tests for quodeq.services.scan_progress: per-dim coverage fields (files_cached, files_project_total)."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress
from quodeq.shared.serialization import to_camel_dict
from tests.services._scan_progress_fixtures import _make_run, _write_status


class TestCoverageFields:
    def test_dims_carry_cached_and_project_total_from_estimates(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 20, "reason": "incremental",
                                     "total": 100, "cached": 80}}),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.files_cached == 80
        assert dim.files_project_total == 100
        # Run-relative totals unchanged: pending dim still reports the estimate count.
        assert dim.files == {"taken": 0, "total": 20}

    def test_running_dim_keeps_coverage_fields_alongside_queue_totals(self, tmp_path: Path) -> None:
        # Queue totals stay run-relative; coverage fields ride the estimate.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], current_dimension="security")
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 20, "reason": "incremental",
                                     "total": 100, "cached": 80}}),
            encoding="utf-8",
        )
        queue_payload = {
            "taken": [{"files": ["a.py", "b.py"], "agent": "a1", "ts": 1}],
            "pending": [f"f{i}.py" for i in range(18)],
        }
        (run_dir / "evidence" / "security_queue.json").write_text(
            json.dumps(queue_payload), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.files == {"taken": 2, "total": 20}
        assert dim.files_cached == 80
        assert dim.files_project_total == 100

    def test_legacy_estimates_normalise_coverage_fields(self, tmp_path: Path) -> None:
        # Old sidecars lack total/cached → total falls back to count, cached 0.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 20, "reason": "incremental"}}),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.files_cached == 0
        assert dim.files_project_total == 20

    def test_no_estimates_file_leaves_coverage_fields_none(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.files_cached is None
        assert dim.files_project_total is None

    def test_progress_to_dict_camel_cases_coverage_fields(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 20, "reason": "incremental",
                                     "total": 100, "cached": 80}}),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        payload = to_camel_dict(progress)
        dim = payload["dimensions"][0]
        assert dim["filesCached"] == 80
        assert dim["filesProjectTotal"] == 100
