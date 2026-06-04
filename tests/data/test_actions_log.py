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
    assert data["payload"] == {"req": "R1", "file": "a.py", "line": 1, "reason": None}


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
