"""Tests for set_deadline propagating into status.json via the lifecycle."""
from pathlib import Path

from quodeq.shared.run_lifecycle import RunLifecycleContext
from quodeq.shared.run_status import read_status


def test_set_deadline_writes_to_status_json(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path,
        job_id="j1",
        dimensions=["a"],
    ) as lifecycle:
        lifecycle.set_deadline("2026-05-02T11:00:00+00:00")
        data = read_status(tmp_path)
        assert data is not None
        assert data["deadline_at"] == "2026-05-02T11:00:00+00:00"


def test_no_deadline_set_writes_none(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path,
        job_id="j1",
        dimensions=["a"],
    ) as lifecycle:
        lifecycle.set_phase("analyzing")
        data = read_status(tmp_path)
        assert data is not None
        assert data.get("deadline_at") is None


def test_set_time_limit_writes_to_status_json(tmp_path: Path) -> None:
    with RunLifecycleContext(
        run_dir=tmp_path,
        job_id="j1",
        dimensions=["a"],
    ) as lifecycle:
        lifecycle.set_time_limit(600)
        data = read_status(tmp_path)
        assert data is not None
        assert data["time_limit_s"] == 600


def test_set_time_limit_zero_preserved(tmp_path: Path) -> None:
    # 0 = unlimited must survive verbatim so readers can distinguish
    # "explicitly unlimited" from "unknown budget" (None).
    with RunLifecycleContext(
        run_dir=tmp_path,
        job_id="j1",
        dimensions=["a"],
    ) as lifecycle:
        lifecycle.set_time_limit(0)
        data = read_status(tmp_path)
        assert data is not None
        assert data["time_limit_s"] == 0
