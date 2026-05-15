"""End-to-end: a synthetic run produces JSONL + event log, projection populates SQLite.

Exercises the full post-dual-write happy path:
  - FindingsRouter writes to JSONL + events.jsonl (via EventLogWriter)
  - ProjectionEngine.rebuild() projects events.jsonl → evaluation.db
  - load_evidence_map prefers the SQLite path when evaluation.db exists
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.fs.report_parser._evidence import load_evidence_map
from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _arg(p: str, line: int, d: str = "timeliness") -> dict:
    return {
        "p": p, "d": d, "file": "src/x.py", "line": line, "t": "violation",
        "severity": "high", "reason": f"reason {p}", "snippet": "code",
        "w": "title",
    }


def test_jsonl_event_log_and_projection_to_sqlite(tmp_path: Path):
    run_dir = tmp_path / "evaluations" / "proj" / "run1"
    run_dir.mkdir(parents=True)
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()

    jsonl_path = evidence_dir / "timeliness_evidence.jsonl"
    events_log = run_dir / "events.jsonl"
    event_log = EventLogWriter(events_log)

    with jsonl_path.open("w") as fh:
        router = FindingsRouter(fh, event_log=event_log)
        router.receive(_arg("P1", 1))
        router.receive(_arg("P2", 2))
        router.receive(_arg("P1", 1))  # duplicate — only 2 findings written

    # JSONL has 2 findings
    lines = [json.loads(line) for line in jsonl_path.read_text().splitlines()]
    assert len(lines) == 2

    # events.jsonl has 2 events
    assert events_log.exists()

    # Before projection, SQLite does not exist
    assert not (run_dir / "evaluation.db").exists()

    # Projection populates SQLite
    ProjectionEngine().rebuild(events_log, run_dir)

    repo = SqliteFindingsRepository(run_dir)
    assert repo.count_by_dimension() == {"timeliness": 2}

    # load_evidence_map prefers SQLite now that evaluation.db exists
    evidence = load_evidence_map(evidence_dir)
    assert "timeliness" in evidence
    principles = evidence["timeliness"]["principles"]
    assert "P1" in principles and "P2" in principles
