"""Tests for quodeq.services.scan_progress — live progress reader.

Focus: the per-dim total resolution path. Pending dims should prefer the
precomputed dim_estimates.json over the project-wide scan.json fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress
from quodeq.shared.serialization import to_camel_dict


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
        dim = progress.dimensions[0]
        assert dim.files["total"] == 0
        assert dim.files_cached is None
        assert dim.files_project_total is None

    def test_non_utf8_dim_estimates_does_not_break_reader(self, tmp_path: Path) -> None:
        # Invalid UTF-8 in the sidecar must not raise out of the reader — the
        # polled progress endpoint would 500 on every request otherwise.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        (run_dir / "dim_estimates.json").write_bytes(b"\xff\xfe\x00garbage")

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        dim = progress.dimensions[0]
        assert dim.files["total"] == 0
        assert dim.files_cached is None
        assert dim.files_project_total is None


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


class TestTotalElapsed:
    def test_naive_started_at_does_not_raise(self, tmp_path: Path) -> None:
        # Legacy/hand-written status.json can carry a naive timestamp.
        # Subtracting it from an aware now() raised TypeError on every
        # progress poll, turning the endpoint into a 500.
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        status["started_at"] = "2026-04-26T12:00:00"  # no tz offset
        (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")

        progress = build_scan_progress("j1", run_dir)
        assert progress is not None
        assert progress.total_elapsed_s is not None
        assert progress.total_elapsed_s >= 0.0


class TestDimElapsed:
    """Per-dim elapsed must come from queue timestamps, not file mtimes.

    The queue file is atomically rewritten on every take (new inode, fresh
    mtime), so an mtime-based start made the running clock reset toward zero
    every few seconds. Done dims read 0:00 because the agent stream files
    (the old end signal) are deleted when the dim completes.
    """

    def _write_queue(self, run_dir: Path, dim: str, payload: dict) -> None:
        (run_dir / "evidence" / f"{dim}_queue.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )

    def test_running_dim_elapsed_from_created_at(self, tmp_path: Path) -> None:
        import time as _t
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        now = _t.time()
        self._write_queue(run_dir, "security", {
            "created_at": now - 300,
            "taken": [{"files": ["a.py"], "agent": "a1", "ts": now - 2}],
            "pending": ["b.py"],
        })
        progress = build_scan_progress("j1", run_dir)
        dim = progress.dimensions[0]
        assert dim.state == "running"
        # mtime of the just-written queue file is "now"; created_at is 5 min ago.
        assert dim.elapsed_s is not None
        assert 295 <= dim.elapsed_s <= 310

    def test_done_dim_elapsed_from_take_log(self, tmp_path: Path) -> None:
        import time as _t
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], state="done")
        now = _t.time()
        self._write_queue(run_dir, "security", {
            "created_at": now - 400,
            "taken": [
                {"files": ["a.py"], "agent": "a1", "ts": now - 350},
                {"files": ["b.py"], "agent": "a1", "ts": now - 100},
            ],
            "pending": [],
        })
        progress = build_scan_progress("j1", run_dir)
        dim = progress.dimensions[0]
        assert dim.state == "done"
        # end >= last take (now-100); start = created_at (now-400) -> >= 300s.
        assert dim.elapsed_s is not None
        assert dim.elapsed_s >= 300

    def test_legacy_queue_without_created_at_uses_first_take(self, tmp_path: Path) -> None:
        import time as _t
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        now = _t.time()
        self._write_queue(run_dir, "security", {
            "taken": [{"files": ["a.py"], "agent": "a1", "ts": now - 120}],
            "pending": ["b.py"],
        })
        progress = build_scan_progress("j1", run_dir)
        dim = progress.dimensions[0]
        assert dim.elapsed_s is not None
        assert 115 <= dim.elapsed_s <= 130


class TestDimElapsedFromStamps:
    """Transition timestamps in dimensions.json beat queue reconstruction.

    write_dim_state stamps started_at/completed_at at the actual state
    transitions, so when both ends exist the duration is exact — the
    queue/mtime forensics stay fallback-only.
    """

    def _write_queue(self, run_dir: Path, dim: str, payload: dict) -> None:
        (run_dir / "evidence" / f"{dim}_queue.json").write_text(
            json.dumps(payload), encoding="utf-8",
        )

    def _write_dim_record(self, run_dir: Path, dim: str, record: dict) -> None:
        (run_dir / "dimensions.json").write_text(
            json.dumps({"schema_version": 1, "dimensions": {dim: record}}),
            encoding="utf-8",
        )

    def test_running_dim_prefers_stamped_started_at(self, tmp_path: Path) -> None:
        import time as _t
        from datetime import datetime, timezone
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"])
        now = _t.time()
        # Queue says the dim started 300s ago; the stamped record says 600s.
        self._write_queue(run_dir, "security", {
            "created_at": now - 300,
            "taken": [{"files": ["a.py"], "agent": "a1", "ts": now - 2}],
            "pending": ["b.py"],
        })
        started = datetime.fromtimestamp(now - 600, tz=timezone.utc).isoformat()
        self._write_dim_record(run_dir, "security", {"state": "running", "started_at": started})
        dim = build_scan_progress("j1", run_dir).dimensions[0]
        assert dim.state == "running"
        assert dim.elapsed_s is not None
        assert 595 <= dim.elapsed_s <= 610

    def test_done_dim_duration_is_stamp_subtraction(self, tmp_path: Path) -> None:
        import time as _t
        from datetime import datetime, timezone
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], state="done")
        now = _t.time()
        # Take log would reconstruct >=300s; the stamps say exactly 250s.
        self._write_queue(run_dir, "security", {
            "created_at": now - 400,
            "taken": [
                {"files": ["a.py"], "agent": "a1", "ts": now - 350},
                {"files": ["b.py"], "agent": "a1", "ts": now - 100},
            ],
            "pending": [],
        })
        iso = lambda s: datetime.fromtimestamp(now - s, tz=timezone.utc).isoformat()  # noqa: E731
        self._write_dim_record(run_dir, "security", {
            "state": "done", "started_at": iso(350), "completed_at": iso(100),
        })
        dim = build_scan_progress("j1", run_dir).dimensions[0]
        assert dim.state == "done"
        assert dim.elapsed_s == 250.0

    def test_interrupted_dim_uses_interrupted_at_as_end(self, tmp_path: Path) -> None:
        import time as _t
        from datetime import datetime, timezone
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], state="cancelled")
        now = _t.time()
        self._write_queue(run_dir, "security", {
            "created_at": now - 400,
            "taken": [{"files": ["a.py"], "agent": "a1", "ts": now - 350}],
            "pending": ["b.py"],
        })
        iso = lambda s: datetime.fromtimestamp(now - s, tz=timezone.utc).isoformat()  # noqa: E731
        self._write_dim_record(run_dir, "security", {
            "state": "incomplete", "started_at": iso(300), "interrupted_at": iso(120),
        })
        dim = build_scan_progress("j1", run_dir).dimensions[0]
        assert dim.elapsed_s == 180.0

    def test_done_dim_without_end_stamp_falls_back_to_reconstruction(self, tmp_path: Path) -> None:
        # A hard kill can leave started_at with no terminal stamp; the queue
        # take-log reconstruction must still produce a number.
        import time as _t
        from datetime import datetime, timezone
        run_dir = _make_run(tmp_path)
        _write_status(run_dir, dimensions=["security"], state="done")
        now = _t.time()
        self._write_queue(run_dir, "security", {
            "created_at": now - 400,
            "taken": [{"files": ["a.py"], "agent": "a1", "ts": now - 100}],
            "pending": [],
        })
        started = datetime.fromtimestamp(now - 350, tz=timezone.utc).isoformat()
        self._write_dim_record(run_dir, "security", {"state": "running", "started_at": started})
        dim = build_scan_progress("j1", run_dir).dimensions[0]
        assert dim.state == "done"
        # created_at (now-400) -> last take (now-100): reconstruction, not stamps.
        assert dim.elapsed_s is not None
        assert dim.elapsed_s >= 295


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
