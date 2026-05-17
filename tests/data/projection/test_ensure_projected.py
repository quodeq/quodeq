from __future__ import annotations

import threading
from pathlib import Path

from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    JudgmentCreatedEvent,
    JudgmentPayload,
)
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.actions_log import ActionLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector
from quodeq.data.sqlite.connection import open_evaluation_db


def _write_events(log: Path, n: int, start: int = 0) -> None:
    writer = EventLogWriter(log)
    for i in range(start, start + n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


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


def _seed_run_with_finding(run_dir: Path, *, req: str, file: str, line: int) -> Path:
    """Write a single JudgmentCreatedEvent into run_dir/events.jsonl. Return the path."""
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file=file, line=line, reason="r", req=req,
    )))
    return log


def _verdict_for(run_dir: Path, req: str, file: str, line: int) -> str | None:
    with open_evaluation_db(run_dir) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE requirement=? AND file=? AND line=?",
            (req, file, line),
        ).fetchone()
    return row[0] if row else None


def test_ensure_replays_actions_jsonl(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "runs" / "r1"
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
    run_dir = project_dir / "runs" / "r1"
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
    run_dir = project_dir / "runs" / "r1"
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
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    # Legacy: dismissed.json exists, actions.jsonl does not.
    (project_dir / "dismissed.json").write_text(
        '[{"req":"R1","file":"a.py","line":10}]', encoding="utf-8",
    )

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # Migration folded the JSON entry into actions.jsonl, projection applied it.
    assert _verdict_for(run_dir, "R1", "a.py", 10) == "dismissed"


def test_ensure_projected_populates_grade_tables(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    from quodeq.data.sqlite.state_store import SQLiteStateStore
    store = SQLiteStateStore(run_dir)
    assert len(store.read_dimension_scores()) == 1
    assert len(store.read_principle_grades()) == 1


def test_ensure_projected_grade_updates_after_dismiss(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    from quodeq.data.sqlite.state_store import SQLiteStateStore
    store = SQLiteStateStore(run_dir)
    # Sanity: grade exists initially.
    assert len(store.read_dimension_scores()) == 1

    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # All findings dismissed → no dimension rows.
    assert store.read_dimension_scores() == []
    assert store.read_principle_grades() == []
