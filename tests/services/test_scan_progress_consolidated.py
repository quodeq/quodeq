"""Tests for quodeq.services.scan_progress: consolidated (grouped) run progress."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress
from tests.services._scan_progress_fixtures import _make_run, _write_status


class TestConsolidatedProgress:
    """Consolidated (grouped) runs write consolidated_* files, not per-dim
    queues, so the per-dim reader showed 0% / "estimating…" for the whole
    run. While such a run is live, progress reports one consolidated row
    with the real file counts."""

    def test_live_consolidated_run_reports_one_real_row(self, tmp_path: Path) -> None:
        import time as _t
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security", "reliability"])
        (run_dir / "evidence" / "consolidated_queue.json").write_text(
            json.dumps({
                "created_at": _t.time() - 60,
                "taken": [{"files": ["a.py", "b.py"], "agent": "a1", "ts": _t.time() - 5}],
                "pending": [f"f{i}.py" for i in range(8)],
            }),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert [d.id for d in progress.dimensions] == ["consolidated"]
        dim = progress.dimensions[0]
        assert dim.state == "running"
        assert dim.files == {"taken": 2, "total": 10}
        assert dim.elapsed_s is not None and dim.elapsed_s >= 55

    def test_per_dimension_run_unaffected(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "evidence" / "security_queue.json").write_text(
            json.dumps({"taken": [], "pending": ["a.py"]}), encoding="utf-8",
        )
        progress = build_scan_progress("j1", run_dir)
        assert [d.id for d in progress.dimensions] == ["security"]

    def test_terminal_consolidated_run_keeps_per_dim_rows(self, tmp_path: Path) -> None:
        # After the run, per-dim evaluation files exist and the normal
        # per-dim classification applies.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], state="done")
        (run_dir / "evidence" / "consolidated_queue.json").write_text(
            json.dumps({"taken": [], "pending": []}), encoding="utf-8",
        )
        (run_dir / "evaluation").mkdir()
        (run_dir / "evaluation" / "security.json").write_text("{}", encoding="utf-8")
        progress = build_scan_progress("j1", run_dir)
        assert [d.id for d in progress.dimensions] == ["security"]
        assert progress.dimensions[0].state == "done"
