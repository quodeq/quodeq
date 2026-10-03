"""Dashboard attaches per-dim exit_reason when available, falls back to run-level."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.dashboard import attach_exit_reason_to_dim, read_run_exit_reason


def test_per_dim_exit_reason_wins_over_run_level():
    dim = {"dimension": "security", "exit_reason": "time_limit"}
    out = attach_exit_reason_to_dim(dim, run_exit_reason="deadline")
    assert out["exitReason"] == "time_limit"


def test_falls_back_to_run_level_when_dim_missing():
    dim = {"dimension": "security"}
    out = attach_exit_reason_to_dim(dim, run_exit_reason="deadline")
    assert out["exitReason"] == "deadline"


def test_no_exit_reason_when_both_absent():
    dim = {"dimension": "security"}
    out = attach_exit_reason_to_dim(dim, run_exit_reason=None)
    assert "exitReason" not in out


class TestReadRunExitReason:
    def test_non_object_status_json_does_not_crash(self, tmp_path: Path):
        """A non-object status.json (e.g. a JSON array) must not crash the
        dashboard: ``read_run_exit_reason`` calls ``.get`` on the parsed
        result unconditionally."""
        run_dir = tmp_path / "proj" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text("[1, 2, 3]", encoding="utf-8")

        assert read_run_exit_reason(tmp_path, "proj", "run-1") is None

    def test_reads_exit_reason(self, tmp_path: Path):
        run_dir = tmp_path / "proj" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "status.json").write_text('{"exit_reason": "deadline"}', encoding="utf-8")

        assert read_run_exit_reason(tmp_path, "proj", "run-1") == "deadline"
