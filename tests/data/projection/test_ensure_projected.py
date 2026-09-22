"""Projector.ensure_projected: size checkpoints, concurrency and actions.jsonl replay."""
from __future__ import annotations

import threading
from pathlib import Path

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    JudgmentCreatedEvent,
    JudgmentPayload,
)
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.actions_log import ActionLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector
from tests.data.projection._ensure_projected_helpers import (
    _seed_run_with_finding,
    _verdict_for,
    _write_events,
)


def test_ensure_no_op_when_size_matches(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    projector = Projector()
    projector.project(log, tmp_path)

    result = projector.ensure_projected(log, tmp_path)

    assert result == ProjectionResult(events_projected=0, rebuilt=False)


def test_ensure_projects_when_size_grows(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    projector = Projector()
    projector.project(log, tmp_path)

    _write_events(log, 3, start=2)
    result = projector.ensure_projected(log, tmp_path)

    assert result.events_projected == 3
    assert result.rebuilt is False


def test_ensure_bootstrap_when_no_size_stored(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 4)

    result = Projector().ensure_projected(log, tmp_path)

    assert result.events_projected == 4
    assert result.rebuilt is True


def test_concurrent_ensure_projects_once(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    # Prime once so both threads see a stored size that doesn't match yet.
    Projector().project(log, tmp_path)
    _write_events(log, 2, start=3)

    projector = Projector()
    call_count = 0
    real_project = projector.project
    call_lock = threading.Lock()

    def spy(*args, **kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        return real_project(*args, **kwargs)

    projector.project = spy  # type: ignore[method-assign]

    barrier = threading.Barrier(2)

    def run() -> None:
        barrier.wait()
        projector.ensure_projected(log, tmp_path)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert call_count == 1


def test_ensure_replays_actions_jsonl(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)

    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().project(events_log, run_dir)
    assert _verdict_for(run_dir, "R1", "a.py", 10) == "violation"

    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    assert _verdict_for(run_dir, "R1", "a.py", 10) == "dismissed"


def test_ensure_no_op_when_actions_log_unchanged(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    projector = Projector()
    projector.project(events_log, run_dir)
    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )
    projector.ensure_projected(events_log, run_dir, project_dir=project_dir)

    result = projector.ensure_projected(events_log, run_dir, project_dir=project_dir)
    assert result.events_projected == 0


def test_ensure_works_without_project_dir(tmp_path: Path) -> None:
    """Callers that don't pass project_dir get today's behavior (events.jsonl only)."""
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    result = Projector().ensure_projected(log, tmp_path)
    assert result.events_projected == 2


def test_ensure_applies_existing_dismissals_to_freshly_scanned_findings(tmp_path: Path) -> None:
    """Regression: when events.jsonl grows but actions.jsonl doesn't, brand-new findings
    must still be matched against pre-existing dismissals.

    Without ``force=events_changed`` in ensure_projected, the size-unchanged fast-path
    in update_actions would skip the replay and the new finding would stay as 'violation'.
    """
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = run_dir / "events.jsonl"

    # Pre-existing dismissal for a key that doesn't exist as a finding yet.
    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )

    # Seed events.jsonl with an unrelated finding so the events checkpoint gets set.
    EventLogWriter(events_log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P0", verdict="violation", dimension="Security",
        file="b.py", line=20, reason="seed", req="R0",
    )))

    # First projection: both logs project. The R1 dismiss is a no-op (no matching finding).
    # Both checkpoints are saved.
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    assert _verdict_for(run_dir, "R1", "a.py", 10) is None
    assert _verdict_for(run_dir, "R0", "b.py", 20) == "violation"

    # Now a re-scan produces the matching finding. actions.jsonl is unchanged.
    EventLogWriter(events_log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",
    )))

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # The pre-existing dismissal applies to the freshly-projected finding.
    assert _verdict_for(run_dir, "R1", "a.py", 10) == "dismissed"


def test_ensure_projected_runs_migration_first(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    # Legacy: dismissed.json exists, actions.jsonl does not.
    (project_dir / "dismissed.json").write_text(
        '[{"req":"R1","file":"a.py","line":10}]', encoding="utf-8",
    )

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # Migration folded the JSON entry into actions.jsonl, projection applied it.
    assert _verdict_for(run_dir, "R1", "a.py", 10) == "dismissed"
