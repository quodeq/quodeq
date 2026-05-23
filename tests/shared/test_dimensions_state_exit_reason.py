"""dimensions.json carries an optional per-dim exit_reason on DONE."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.shared.dimensions_state import DimState, read_dimensions, write_dim_state


def test_write_dim_state_persists_exit_reason_on_done(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_dim_state(run_dir, "security", DimState.DONE, exit_reason="time_limit")
    raw = json.loads((run_dir / "dimensions.json").read_text(encoding="utf-8"))
    assert raw["dimensions"]["security"]["exit_reason"] == "time_limit"
    assert raw["dimensions"]["security"]["state"] == "done"


def test_read_dimensions_returns_exit_reason(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_dim_state(run_dir, "security", DimState.DONE, exit_reason="time_limit")
    state = read_dimensions(run_dir)
    assert state["dimensions"]["security"]["exit_reason"] == "time_limit"


def test_write_dim_state_omits_exit_reason_when_none(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_dim_state(run_dir, "security", DimState.DONE)
    raw = json.loads((run_dir / "dimensions.json").read_text(encoding="utf-8"))
    assert "exit_reason" not in raw["dimensions"]["security"]


def test_exit_reason_ignored_for_non_done_states(tmp_path: Path):
    """exit_reason only attaches to DONE; RUNNING/INCOMPLETE use different fields."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_dim_state(run_dir, "security", DimState.RUNNING, exit_reason="ignored")
    raw = json.loads((run_dir / "dimensions.json").read_text(encoding="utf-8"))
    assert "exit_reason" not in raw["dimensions"]["security"]
