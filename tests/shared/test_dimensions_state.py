from __future__ import annotations
import json
from pathlib import Path

import pytest

from quodeq.data.fs.dimensions_state_store import (
    DimState,
    IllegalDimTransitionError,
    read_dimensions,
    write_dim_state,
)


class TestStateMachine:
    def test_initial_state_is_pending(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        data = read_dimensions(tmp_path)
        assert data["dimensions"]["security"]["state"] == "pending"

    def test_pending_to_running_to_done(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.DONE)
        assert read_dimensions(tmp_path)["dimensions"]["security"]["state"] == "done"

    def test_running_to_incomplete_with_reason(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.INCOMPLETE, reason="cancelled_by_user")
        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "incomplete"
        assert entry["reason"] == "cancelled_by_user"

    def test_done_is_terminal(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "security", DimState.DONE)
        with pytest.raises(IllegalDimTransitionError):
            write_dim_state(tmp_path, "security", DimState.RUNNING)

    def test_pending_to_done_illegal(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        with pytest.raises(IllegalDimTransitionError):
            write_dim_state(tmp_path, "security", DimState.DONE)

    def test_multiple_dims_independent(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        write_dim_state(tmp_path, "reliability", DimState.PENDING)
        data = read_dimensions(tmp_path)
        assert data["dimensions"]["security"]["state"] == "running"
        assert data["dimensions"]["reliability"]["state"] == "pending"

    def test_atomic_write_rename(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        # No leftover .tmp files.
        assert not (tmp_path / "dimensions.json.tmp").exists()


class TestTransitionTimestampsPreserved:
    """Transitions merge into the record; earlier stamps survive.

    Progress derives a dimension's duration as completed_at - started_at,
    which only works if the DONE write doesn't wipe the RUNNING stamp."""

    def test_started_at_survives_done(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        started = read_dimensions(tmp_path)["dimensions"]["security"]["started_at"]
        write_dim_state(tmp_path, "security", DimState.DONE, exit_reason="done")
        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "done"
        assert entry["started_at"] == started
        assert entry["completed_at"]
        assert entry["exit_reason"] == "done"

    def test_started_at_survives_incomplete(self, tmp_path: Path):
        write_dim_state(tmp_path, "security", DimState.PENDING)
        write_dim_state(tmp_path, "security", DimState.RUNNING)
        started = read_dimensions(tmp_path)["dimensions"]["security"]["started_at"]
        write_dim_state(tmp_path, "security", DimState.INCOMPLETE, reason="cancelled_by_user")
        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["started_at"] == started
        assert entry["interrupted_at"]
        assert entry["reason"] == "cancelled_by_user"


class TestRead:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert read_dimensions(tmp_path) == {"schema_version": 1, "dimensions": {}}

    def test_corrupt_file_returns_empty(self, tmp_path: Path):
        (tmp_path / "dimensions.json").write_text("{not json")
        assert read_dimensions(tmp_path) == {"schema_version": 1, "dimensions": {}}

    def test_non_utf8_file_returns_empty(self, tmp_path: Path):
        """Regression: a corrupt/non-UTF-8 dimensions.json must degrade the
        same way a missing one does, not raise UnicodeDecodeError and crash
        callers like build_job_snapshot."""
        (tmp_path / "dimensions.json").write_bytes(b"\xff\xfe\x00\x01")
        assert read_dimensions(tmp_path) == {"schema_version": 1, "dimensions": {}}
