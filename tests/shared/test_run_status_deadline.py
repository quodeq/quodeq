"""Tests for deadline_at in status.json writes."""
from pathlib import Path

from quodeq.shared.run_status import RunState, read_status, write_status


def _common(run_dir: Path):
    return dict(
        run_dir=run_dir,
        state=RunState.RUNNING,
        job_id="j1",
        started_at="2026-05-02T10:00:00+00:00",
        dimensions=["a", "b"],
    )


def test_write_status_records_deadline(tmp_path: Path) -> None:
    write_status(**_common(tmp_path), deadline_at="2026-05-02T10:10:00+00:00")
    data = read_status(tmp_path)
    assert data is not None
    assert data["deadline_at"] == "2026-05-02T10:10:00+00:00"


def test_write_status_deadline_default_none(tmp_path: Path) -> None:
    write_status(**_common(tmp_path))
    data = read_status(tmp_path)
    assert data is not None
    assert data.get("deadline_at") is None
