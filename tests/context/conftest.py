"""Shared helpers for context-layer tests."""
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.dismissed import dismiss_finding


def seed_dismissed(
    project_dir: Path,
    run_id: str,
    *,
    req: str,
    snippet: str,
    file: str,
    line: int,
    scope: str | None = None,
) -> Path:
    """Seed a violation into a run, dismiss it, then project into SQL.

    *scope* lets a test seed a scope-level finding (excluded from the
    semantic-precedent tier -- see ``_semantic_eligible`` /
    ``_collect_dismissed_texts``); defaults to None for a normal,
    line-level finding.
    """
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file=file, line=line, reason="r", req=req, snippet=snippet, scope=scope,
    )))
    dismiss_finding(project_dir, {"req": req, "file": file, "line": line})
    Projector().ensure_projected(log, run_dir, project_dir=project_dir)
    return run_dir
