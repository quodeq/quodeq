from __future__ import annotations

import time
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector
from quodeq.data.sqlite.connection import open_evaluation_db


def _write_events(log: Path, n: int) -> None:
    writer = EventLogWriter(log)
    for i in range(n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


def test_project_rebuilds_when_no_checkpoint(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    result = Projector().project(log, tmp_path)
    assert result == ProjectionResult(events_projected=3, rebuilt=True)
    with open_evaluation_db(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 3


def test_project_updates_when_checkpoint_exists(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    writer = EventLogWriter(log)
    p1 = JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f1.py", line=1, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p1))

    Projector().project(log, tmp_path)  # first: no checkpoint, rebuilds

    time.sleep(0.01)

    p2 = JudgmentPayload(
        practice_id="P2", verdict="violation", dimension="Security",
        file="f2.py", line=2, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p2))

    result = Projector().project(log, tmp_path)  # second: checkpoint exists, updates
    assert result == ProjectionResult(events_projected=1, rebuilt=False)
    with open_evaluation_db(tmp_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 2


def test_project_force_rebuild_ignores_checkpoint(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    projector = Projector()
    projector.project(log, tmp_path)  # sets checkpoint
    result = projector.project(log, tmp_path, force_rebuild=True)
    assert result == ProjectionResult(events_projected=2, rebuilt=True)


def test_project_no_new_events_returns_zero(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 1)
    projector = Projector()
    projector.project(log, tmp_path)
    result = projector.project(log, tmp_path)
    assert result == ProjectionResult(events_projected=0, rebuilt=False)


def test_project_raises_when_events_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Projector().project(tmp_path / "nonexistent.jsonl", tmp_path)
