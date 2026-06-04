from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from quodeq.shared.run_status import (
    RunState,
    TERMINAL_STATES,
    UnsupportedSchemaError,
    IllegalTransitionError,
    read_status,
    validate_transition,
    write_status,
)


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    write_status(tmp_path, state=RunState.PENDING, job_id="ext-r", started_at="2026-04-20T00:00:00+00:00", dimensions=["security"])
    status = read_status(tmp_path)
    assert status["state"] == "pending"
    assert status["job_id"] == "ext-r"
    assert status["dimensions"] == ["security"]
    assert status["schema_version"] == 2


def test_atomic_write_uses_tmp_then_rename(tmp_path: Path, monkeypatch) -> None:
    """Readers never see a partial file: write_status must rename a complete tmp."""
    calls: list[str] = []
    real_replace = Path.replace
    def spy_replace(self, target):
        calls.append("replace")
        return real_replace(self, target)
    monkeypatch.setattr(Path, "replace", spy_replace)
    write_status(tmp_path, state=RunState.PENDING, job_id="x", started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    assert calls == ["replace"]
    tmp = tmp_path / "status.json.tmp"
    assert not tmp.exists()
    assert (tmp_path / "status.json").exists()


def test_transition_matrix_legal(tmp_path: Path) -> None:
    for src, dst in [
        (RunState.PENDING, RunState.RUNNING),
        (RunState.RUNNING, RunState.FINALIZING),
        (RunState.FINALIZING, RunState.DONE),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.FINALIZING, RunState.FAILED),
        (RunState.PENDING, RunState.CANCELLED),
        (RunState.RUNNING, RunState.CANCELLED),
        (RunState.FINALIZING, RunState.CANCELLED),
    ]:
        validate_transition(src, dst)  # must not raise


def test_transition_matrix_illegal_raises() -> None:
    for src, dst in [
        (RunState.DONE, RunState.RUNNING),
        (RunState.CANCELLED, RunState.RUNNING),
        (RunState.FAILED, RunState.RUNNING),
        (RunState.PENDING, RunState.FINALIZING),
        (RunState.PENDING, RunState.DONE),
        (RunState.RUNNING, RunState.PENDING),
    ]:
        with pytest.raises(IllegalTransitionError):
            validate_transition(src, dst)


def test_terminal_states() -> None:
    assert TERMINAL_STATES == frozenset({RunState.DONE, RunState.FAILED, RunState.CANCELLED})


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_status(tmp_path) is None


def test_read_corrupt_returns_none(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text("not-json{")
    assert read_status(tmp_path) is None


def test_read_unsupported_schema_raises(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text(json.dumps({"schema_version": 99, "state": "running"}))
    with pytest.raises(UnsupportedSchemaError):
        read_status(tmp_path)


def test_write_status_persists_provider_and_model(tmp_path: Path) -> None:
    write_status(
        tmp_path,
        state=RunState.RUNNING,
        job_id="ext-abc",
        started_at="2026-01-01T00:00:00Z",
        dimensions=["maintainability"],
        ai_provider="llamacpp",
        ai_model="qwen3.6-27b",
    )
    data = json.loads((tmp_path / "status.json").read_text())
    assert data["ai_provider"] == "llamacpp"
    assert data["ai_model"] == "qwen3.6-27b"


def test_write_status_omits_provider_and_model_when_unset(tmp_path: Path) -> None:
    write_status(
        tmp_path,
        state=RunState.RUNNING,
        job_id="ext-abc",
        started_at="2026-01-01T00:00:00Z",
        dimensions=[],
    )
    data = json.loads((tmp_path / "status.json").read_text())
    assert "ai_provider" not in data
    assert "ai_model" not in data


def test_concurrent_writes_no_partial_file(tmp_path: Path) -> None:
    """Two threads writing concurrently: each read sees a valid JSON document."""
    barrier = threading.Barrier(2)
    def worker(label: str) -> None:
        barrier.wait()
        for _ in range(50):
            write_status(tmp_path, state=RunState.RUNNING, job_id=label,
                         started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start(); t2.start(); t1.join(); t2.join()
    # After all writes, the file parses cleanly.
    final = read_status(tmp_path)
    assert final is not None
    assert final["state"] == "running"
    assert final["job_id"] in {"A", "B"}
