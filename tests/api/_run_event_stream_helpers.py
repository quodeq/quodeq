"""Run-directory writers for tests/api/test_run_event_stream*.py siblings."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter


def _write_status(run_dir: Path, state: str = "running") -> None:
    (run_dir / "status.json").write_text(json.dumps({"state": state}))


def _write_dim_eval(run_dir: Path, dim: str, score: int = 90) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / f"{dim}.json").write_text(
        json.dumps({"dimension": dim, "score": score}),
    )


def _write_finding_event(run_dir: Path, p: str = "P1", line: int = 1) -> None:
    event_log = EventLogWriter(run_dir / "events.jsonl")
    payload = JudgmentPayload(
        practice_id=p,
        verdict="violation",
        dimension="dim",
        file="x.py",
        line=line,
        reason="r",
        severity="medium",
        snippet="s",
        title="t",
    )
    event_log.emit(JudgmentCreatedEvent(payload=payload))
