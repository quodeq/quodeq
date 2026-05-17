"""Tests for the dismissed findings storage service."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.dismissed import (
    dismiss_finding,
    dismissed_keys,
    restore_finding,
)


def _seed_run(project_dir: Path, run_id: str, *, req: str, file: str, line: int) -> Path:
    run_dir = project_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file=file, line=line, reason="r", req=req,
    )))
    # Project events.jsonl into evaluation.db so SQL reads work.
    Projector().project(log, run_dir)
    return run_dir


def test_dismiss_finding_appends_to_actions_log(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    log = project_dir / "actions.jsonl"
    assert log.exists()
    assert "FINDING_DISMISSED" in log.read_text()
    assert '"req":"R1"' in log.read_text().replace(" ", "")


def test_restore_finding_appends_undismiss_event(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    restore_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    text = (project_dir / "actions.jsonl").read_text()
    assert text.count("FINDING_DISMISSED") == 1
    assert text.count("FINDING_UNDISMISSED") == 1


def test_dismissed_keys_aggregates_across_runs(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    r1_dir = _seed_run(project_dir, "r1", req="R1", file="a.py", line=10)
    r2_dir = _seed_run(project_dir, "r2", req="R2", file="b.py", line=20)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})
    dismiss_finding(project_dir, {"req": "R2", "file": "b.py", "line": 20})
    # Apply the action log onto each run's DB.
    Projector().ensure_projected(r1_dir / "events.jsonl", r1_dir, project_dir=project_dir)
    Projector().ensure_projected(r2_dir / "events.jsonl", r2_dir, project_dir=project_dir)

    keys = dismissed_keys(project_dir)

    assert keys == {("R1", "a.py", 10), ("R2", "b.py", 20)}


def test_dismissed_keys_empty_when_no_runs(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert dismissed_keys(project_dir) == set()
