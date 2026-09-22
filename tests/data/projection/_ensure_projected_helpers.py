"""Event-log seeding helpers for tests/data/projection/test_ensure_projected*.py siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.sqlite.connection import open_evaluation_db


def _write_events(log: Path, n: int, start: int = 0) -> None:
    writer = EventLogWriter(log)
    for i in range(start, start + n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


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
