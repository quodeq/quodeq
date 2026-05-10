from __future__ import annotations
import json
from pathlib import Path

import pytest

from quodeq.shared.dimensions_state import (
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


class TestRead:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert read_dimensions(tmp_path) == {"schema_version": 1, "dimensions": {}}

    def test_corrupt_file_returns_empty(self, tmp_path: Path):
        (tmp_path / "dimensions.json").write_text("{not json")
        assert read_dimensions(tmp_path) == {"schema_version": 1, "dimensions": {}}
