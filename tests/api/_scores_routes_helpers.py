"""Run-seeding helpers for tests/api/test_scores_routes*.py siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector


def _seed_run(
    reports_root: Path,
    project: str,
    run_id: str,
    violations: list[dict] | None = None,
    project_after: bool = True,
) -> Path:
    """Create run directory, write events.jsonl, optionally trigger projection."""
    run_dir = reports_root / project / run_id
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    for v in (violations or []):
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**v)))
    if project_after:
        project_dir = reports_root / project
        Projector().ensure_projected(log, run_dir, project_dir=project_dir)
    return run_dir


_DEFAULT_VIOLATION = dict(
    practice_id="P1", verdict="violation", dimension="Security",
    file="a.py", line=10, reason="weak hash", req="R1", severity="high",
)


def _scorable_violations(n: int = 5, *, practice: str = "P1", dimension: str = "Security") -> list[dict]:
    """N distinct violations for the same principle — enough to clear the
    medium-confidence floor in ``classify_confidence_level`` so the
    projector scores the principle instead of returning Insufficient."""
    return [
        dict(
            practice_id=practice, verdict="violation", dimension=dimension,
            file=f"f{i}.py", line=10 + i, reason="r", req=f"R{i}",
            severity="high",
        )
        for i in range(n)
    ]
