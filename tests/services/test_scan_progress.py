"""Tests for quodeq.services.scan_progress — live progress reader.

Focus: the per-dim total resolution path. Pending dims should prefer the
precomputed dim_estimates.json over the project-wide scan.json fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress


def _write_status(run_dir: Path, *, dimensions: list[str], state: str = "running",
                  current_dimension: str | None = None) -> None:
    status = {
        "schema_version": 1,
        "job_id": "j1",
        "state": state,
        "started_at": "2026-04-26T12:00:00+00:00",
        "dimensions": dimensions,
        "phase": "analyzing",
        "current_dimension": current_dimension,
    }
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def _make_run(tmp_path: Path) -> Path:
    """Create a project_dir / run_dir layout with the directories the reader expects."""
    project_dir = tmp_path / "project"
    run_dir = project_dir / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    return run_dir


class TestPendingDimTotals:
    def test_pending_dim_uses_precomputed_estimate(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security", "reliability"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({
                "security": {"count": 827, "reason": "incremental"},
                "reliability": {"count": 412, "reason": "catching-up"},
            }),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        totals = {d.id: d.files["total"] for d in progress.dimensions}
        reasons = {d.id: d.estimate_reason for d in progress.dimensions}
        assert totals == {"security": 827, "reliability": 412}
        assert reasons == {"security": "incremental", "reliability": "catching-up"}

    def test_legacy_int_estimate_format_still_read(self, tmp_path: Path) -> None:
        # Pre-reason runs persisted bare ints. Reader must still surface the
        # count so the header total stays accurate; reason is empty.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": 270}), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert progress.dimensions[0].files["total"] == 270
        assert progress.dimensions[0].estimate_reason == ""

    def test_pending_dim_reports_zero_when_no_estimate_available(self, tmp_path: Path) -> None:
        # Without dim_estimates.json, pending dims report total=0. The UI
        # treats that as "estimates not ready yet" and stays in preparing…
        # rather than printing a misleading project-wide ceiling.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir.parent / "scan.json").write_text(
            json.dumps({"total_files": 1682}), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert progress.dimensions[0].files["total"] == 0

    def test_running_dim_uses_queue_total_not_estimate(self, tmp_path: Path) -> None:
        # Once a queue exists, the actual queue size wins — the estimate was
        # only ever a placeholder for "before the dim ran".
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], current_dimension="security")
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 999, "reason": "incremental"}}),
            encoding="utf-8",
        )
        # Queue says actual = 50 files (3 taken + 47 pending).
        queue_payload = {
            "taken": [{"files": ["a.py", "b.py", "c.py"], "agent": "a1", "ts": 1}],
            "pending": [f"f{i}.py" for i in range(47)],
        }
        (run_dir / "evidence" / "security_queue.json").write_text(
            json.dumps(queue_payload), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.state == "running"
        assert dim.files == {"taken": 3, "total": 50}

    def test_estimate_zero_is_distinct_from_missing(self, tmp_path: Path) -> None:
        # An explicit 0 in dim_estimates means "this dim has no work" —
        # don't fall through to project_files.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 0, "reason": "empty"}}),
            encoding="utf-8",
        )
        (run_dir.parent / "scan.json").write_text(
            json.dumps({"total_files": 1682}), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert progress.dimensions[0].files["total"] == 0

    def test_corrupt_dim_estimates_does_not_break_reader(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_text("{not json", encoding="utf-8")
        (run_dir.parent / "scan.json").write_text(
            json.dumps({"total_files": 100}), encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        # Corrupt estimates → empty dict → pending dim reports 0 (preparing…).
        assert progress.dimensions[0].files["total"] == 0


def _write_dimensions_json(run_dir: Path, states: dict[str, str]) -> None:
    payload = {
        "schema_version": 1,
        "dimensions": {d: {"state": s} for d, s in states.items()},
    }
    (run_dir / "dimensions.json").write_text(json.dumps(payload), encoding="utf-8")


class TestEmptyStatusDimensionsRecovery:
    """Runs launched with *all* dimensions (no --dimensions filter) record an
    empty ``dimensions: []`` in status.json: the raw, unresolved filter is None
    and gets coerced to [] before the lifecycle writes it. The reader must
    recover the dim list from the per-dim sidecars (dimensions.json,
    dim_estimates.json), otherwise the progress header total — and the ETA the
    UI derives from it — collapse to zero for the entire run (PROGRESS stuck on
    "preparing…", no ETA ever shown).
    """

    def test_recovers_dims_from_sidecars_when_status_empty(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=[])  # the bug condition
        _write_dimensions_json(run_dir, {"security": "pending", "reliability": "pending"})
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({
                "security": {"count": 5, "reason": "first-run"},
                "reliability": {"count": 7, "reason": "first-run"},
            }),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        totals = {d.id: d.files["total"] for d in progress.dimensions}
        # Non-zero header total → the ETA can compute instead of preparing…
        assert totals == {"security": 5, "reliability": 7}

    def test_recovers_from_estimates_alone(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=[])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({"security": {"count": 5, "reason": "first-run"}}),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert [d.id for d in progress.dimensions] == ["security"]
        assert progress.dimensions[0].files["total"] == 5

    def test_recovers_running_dim_from_dimensions_json_alone(self, tmp_path: Path) -> None:
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=[])
        _write_dimensions_json(run_dir, {"security": "running"})
        (run_dir / "evidence" / "security_queue.json").write_text(
            json.dumps({
                "taken": [{"files": ["a.py", "b.py"], "agent": "a1", "ts": 1}],
                "pending": ["c.py"],
            }),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert [d.id for d in progress.dimensions] == ["security"]
        assert progress.dimensions[0].files == {"taken": 2, "total": 3}

    def test_explicit_status_dims_take_precedence_over_fallback(self, tmp_path: Path) -> None:
        # When status.json *does* carry a list, the fallback must not fire or
        # add dims from the sidecars — the explicit (possibly filtered) list wins.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["reliability"])
        (run_dir / "dim_estimates.json").write_text(
            json.dumps({
                "security": {"count": 5, "reason": "first-run"},
                "reliability": {"count": 7, "reason": "first-run"},
            }),
            encoding="utf-8",
        )

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert [d.id for d in progress.dimensions] == ["reliability"]

    def test_empty_status_and_no_sidecars_stays_empty(self, tmp_path: Path) -> None:
        # Nothing to recover from → empty list, no crash.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=[])

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert progress.dimensions == []
