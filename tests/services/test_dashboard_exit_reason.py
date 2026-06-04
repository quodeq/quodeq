"""Dashboard attaches per-dim exit_reason when available, falls back to run-level."""
from __future__ import annotations

from quodeq.services.dashboard import _attach_exit_reason_to_dim


def test_per_dim_exit_reason_wins_over_run_level():
    dim = {"dimension": "security", "exit_reason": "time_limit"}
    out = _attach_exit_reason_to_dim(dim, run_exit_reason="deadline")
    assert out["exitReason"] == "time_limit"


def test_falls_back_to_run_level_when_dim_missing():
    dim = {"dimension": "security"}
    out = _attach_exit_reason_to_dim(dim, run_exit_reason="deadline")
    assert out["exitReason"] == "deadline"


def test_no_exit_reason_when_both_absent():
    dim = {"dimension": "security"}
    out = _attach_exit_reason_to_dim(dim, run_exit_reason=None)
    assert "exitReason" not in out
