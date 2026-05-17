"""End-to-end: dismiss via API → SSE tick emits scores.updated within one cycle."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.api._run_event_stream import WatcherState, compute_tick
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.dismissed import dismiss_finding


def test_dismiss_triggers_scores_updated_on_next_tick(tmp_path: Path) -> None:
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)

    # Seed a finding.
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="high",
    )))
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    # Baseline tick captures current grade.
    state = WatcherState()
    _, state = compute_tick(run_dir, state)

    # User dismisses.
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    # Next tick should fire scores.updated with the new (post-dismiss) payload.
    events, _ = compute_tick(run_dir, state)
    grade_events = [e for e in events if e[0] == "scores.updated"]

    assert len(grade_events) == 1, f"Expected scores.updated event after dismiss, got: {[e[0] for e in events]}"

    # The payload should reflect the dismiss.
    payload = json.loads(grade_events[0][1])
    security = next((d for d in payload.get("dimensions", []) if d.get("dimension") == "Security"), None)
    # After dismissal of the only finding, Security may have no row OR have a None/null score.
    assert security is None or security.get("overallScore") is None


def test_grade_no_change_does_not_emit_scores_updated(tmp_path: Path) -> None:
    """Ticks without grade changes do not emit scores.updated."""
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)

    # Seed two findings with critical and low severities in separate dimensions.
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f0.py", line=10, reason="r", req="R0", severity="critical",
    )))
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P2", verdict="violation", dimension="Reliability",
        file="f1.py", line=10, reason="r", req="R1", severity="low",
    )))
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    state = WatcherState()
    _, state = compute_tick(run_dir, state)

    # Dismiss the Security critical finding — should trigger scores.updated.
    dismiss_finding(project_dir, {"req": "R0", "file": "f0.py", "line": 10})
    events1, state = compute_tick(run_dir, state)
    assert len([e for e in events1 if e[0] == "scores.updated"]) == 1

    # Dismiss the Reliability low finding — also triggers (dimension removed).
    dismiss_finding(project_dir, {"req": "R1", "file": "f1.py", "line": 10})
    events2, state = compute_tick(run_dir, state)
    assert len([e for e in events2 if e[0] == "scores.updated"]) == 1

    # No dismiss + tick — should NOT emit (no grade change).
    events3, _ = compute_tick(run_dir, state)
    assert len([e for e in events3 if e[0] == "scores.updated"]) == 0
