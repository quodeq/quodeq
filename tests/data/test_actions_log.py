from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.data.actions_log import ActionLogWriter, read_action_events


def test_writer_appends_event(tmp_path: Path) -> None:
    writer = ActionLogWriter(tmp_path)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=1)))

    log = tmp_path / "actions.jsonl"
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event_type"] == "FINDING_DISMISSED"
    assert data["payload"] == {
        "req": "R1", "file": "a.py", "line": 1, "reason": None, "fingerprint": None,
    }


def test_writer_appends_multiple_events_preserves_order(tmp_path: Path) -> None:
    writer = ActionLogWriter(tmp_path)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=1)))
    writer.emit(FindingUndismissedEvent(payload=FindingUndismissed(req="R1", file="a.py", line=1)))
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R2", file="b.py", line=2)))

    log = tmp_path / "actions.jsonl"
    lines = log.read_text().splitlines()
    assert len(lines) == 3
    types = [json.loads(line)["event_type"] for line in lines]
    assert types == ["FINDING_DISMISSED", "FINDING_UNDISMISSED", "FINDING_DISMISSED"]


def test_writer_creates_parent_dir(tmp_path: Path) -> None:
    project_dir = tmp_path / "nested" / "project"
    writer = ActionLogWriter(project_dir)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=1)))
    assert (project_dir / "actions.jsonl").exists()


def test_read_returns_empty_when_no_log(tmp_path: Path) -> None:
    events = list(read_action_events(tmp_path))
    assert events == []


def test_read_parses_back_to_event_objects(tmp_path: Path) -> None:
    writer = ActionLogWriter(tmp_path)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=1)))
    writer.emit(FindingUndismissedEvent(payload=FindingUndismissed(req="R1", file="a.py", line=1)))

    events = list(read_action_events(tmp_path))
    assert len(events) == 2
    assert isinstance(events[0], FindingDismissedEvent)
    assert events[0].payload.req == "R1"
    assert isinstance(events[1], FindingUndismissedEvent)


def test_read_skips_malformed_lines(tmp_path: Path) -> None:
    log = tmp_path / "actions.jsonl"
    writer = ActionLogWriter(tmp_path)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=1)))
    with log.open("a", encoding="utf-8") as f:
        f.write("not-json\n")
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="R2", file="b.py", line=2)))

    events = list(read_action_events(tmp_path))
    assert len(events) == 2
    assert events[0].payload.req == "R1"
    assert events[1].payload.req == "R2"


class _CountingLock:
    """Stands in for the platform file lock; records how often a write took it."""

    def __init__(self) -> None:
        self.acquired = 0

    def acquire(self, f) -> None:
        self.acquired += 1

    def release(self, f) -> None:
        pass


def _undismiss(*reqs: str) -> list[FindingUndismissedEvent]:
    return [
        FindingUndismissedEvent(payload=FindingUndismissed(req=req, file="a.py", line=1))
        for req in reqs
    ]


def test_emit_many_appends_every_event_in_order(tmp_path: Path) -> None:
    ActionLogWriter(tmp_path).emit_many(_undismiss("R1", "R2", "R3"))

    lines = (tmp_path / "actions.jsonl").read_text().splitlines()
    assert [json.loads(line)["payload"]["req"] for line in lines] == ["R1", "R2", "R3"]


def test_emit_many_takes_the_file_lock_once_for_the_whole_batch(tmp_path: Path, monkeypatch) -> None:
    lock = _CountingLock()
    monkeypatch.setattr("quodeq.data.actions_log.get_file_lock", lambda: lock)

    ActionLogWriter(tmp_path).emit_many(_undismiss("R1", "R2", "R3"))

    assert lock.acquired == 1


def test_emit_many_with_no_events_touches_nothing(tmp_path: Path) -> None:
    ActionLogWriter(tmp_path).emit_many([])
    assert not (tmp_path / "actions.jsonl").exists()


def test_emit_many_serializes_before_writing_so_a_bad_event_leaves_the_log_untouched(
    tmp_path: Path,
) -> None:
    writer = ActionLogWriter(tmp_path)
    with pytest.raises(TypeError):
        writer.emit_many([*_undismiss("R1"), object()])  # type: ignore[list-item]
    assert not (tmp_path / "actions.jsonl").exists()


def test_emit_many_reads_back_as_typed_events(tmp_path: Path) -> None:
    ActionLogWriter(tmp_path).emit_many(_undismiss("R1", "R2"))

    events = list(read_action_events(tmp_path))
    assert [e.payload.req for e in events] == ["R1", "R2"]
    assert all(isinstance(e, FindingUndismissedEvent) for e in events)
