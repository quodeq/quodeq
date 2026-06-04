"""End-to-end: dismiss via service → next read shows dismissed verdict."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.dismissed import dismiss_finding, restore_finding


def test_full_dismiss_flow(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)

    # Seed a finding from the scan.
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",
    )))

    repo = SqliteFindingsRepository(run_dir)
    findings = repo.list_by_dimension("Security")
    assert len(findings) == 1
    assert findings[0].verdict == "violation"

    # Dismiss via the service (what the API route calls).
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    findings = repo.list_by_dimension("Security")
    assert findings[0].verdict == "dismissed"

    # Restore.
    restore_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    findings = repo.list_by_dimension("Security")
    assert findings[0].verdict == "violation"
