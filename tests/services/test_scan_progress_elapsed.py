"""Tests for quodeq.services.scan_progress: total and per-dim elapsed time resolution."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.scan_progress import build_scan_progress
from tests.services._scan_progress_fixtures import _make_run, _write_status


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
