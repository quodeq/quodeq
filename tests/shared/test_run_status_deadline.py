"""Tests for deadline_at in status.json writes."""
from pathlib import Path

from quodeq.data.fs.run_status_store import RunState, RunStatus, read_status, write_status


def _common(**overrides) -> RunStatus:
    fields = dict(
        state=RunState.RUNNING,
        job_id="j1",
        started_at="2026-05-02T10:00:00+00:00",
        dimensions=["a", "b"],
    )
    fields.update(overrides)
    return RunStatus(**fields)


def test_write_status_records_deadline(tmp_path: Path) -> None:
    write_status(tmp_path, _common(deadline_at="2026-05-02T10:10:00+00:00"))
    data = read_status(tmp_path)
    assert data is not None
    assert data["deadline_at"] == "2026-05-02T10:10:00+00:00"


def test_write_status_deadline_default_none(tmp_path: Path) -> None:
    write_status(tmp_path, _common())
    data = read_status(tmp_path)
    assert data is not None
    assert data.get("deadline_at") is None
