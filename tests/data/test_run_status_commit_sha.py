"""``status.json`` carries the commit the run evaluated, when known."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.state import RunState, RunStatus
from quodeq.data.fs.run_status_store import read_status, write_status

_SHA = "0123456789abcdef0123456789abcdef01234567"


def _status(**overrides) -> RunStatus:
    base = {"state": RunState.RUNNING, "job_id": "j", "started_at": "2026-09-26T00:00:00Z",
            "dimensions": ["security"]}
    return RunStatus(**{**base, **overrides})


def test_status_file_carries_commit_sha(tmp_path: Path) -> None:
    write_status(tmp_path, _status(commit_sha=_SHA))
    assert read_status(tmp_path)["commit_sha"] == _SHA


def test_status_file_omits_missing_commit_sha(tmp_path: Path) -> None:
    write_status(tmp_path, _status())
    assert "commit_sha" not in read_status(tmp_path)


def test_from_status_dict_round_trips_commit_sha(tmp_path: Path) -> None:
    write_status(tmp_path, _status(commit_sha=_SHA))
    assert RunStatus.from_status_dict(read_status(tmp_path)).commit_sha == _SHA


def test_status_file_carries_the_dirty_flag(tmp_path: Path) -> None:
    write_status(tmp_path, _status(commit_sha=_SHA, commit_dirty=True))
    assert read_status(tmp_path)["commit_dirty"] is True
    assert RunStatus.from_status_dict(read_status(tmp_path)).commit_dirty is True


def test_status_file_omits_an_unknown_dirty_flag(tmp_path: Path) -> None:
    write_status(tmp_path, _status())
    assert "commit_dirty" not in read_status(tmp_path)
