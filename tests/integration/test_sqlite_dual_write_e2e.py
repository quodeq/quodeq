"""End-to-end: a synthetic run produces JSONL and SQLite that agree.

Exercises the full Plan-1 happy path:
  - FindingsRouter dual-writes findings to JSONL + evaluation.db
  - load_evidence_map prefers the SQLite path when evaluation.db exists
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.data.fs.report_parser._evidence import load_evidence_map
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _arg(p: str, line: int, d: str = "timeliness") -> dict:
    return {
        "p": p, "d": d, "file": "src/x.py", "line": line, "t": "violation",
        "severity": "high", "reason": f"reason {p}", "snippet": "code",
        "w": "title",
    }


def test_dual_write_and_sqlite_first_read(tmp_path: Path):
    run_dir = tmp_path / "evaluations" / "proj" / "run1"
    run_dir.mkdir(parents=True)
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir()

    jsonl_path = evidence_dir / "timeliness_evidence.jsonl"
    repo = SqliteFindingsRepository(run_dir)

    with jsonl_path.open("w") as fh:
        router = FindingsRouter(fh, findings_repo=repo)
        router.receive(_arg("P1", 1))
        router.receive(_arg("P2", 2))
        router.receive(_arg("P1", 1))  # duplicate

    # JSONL written
    lines = [json.loads(line) for line in jsonl_path.read_text().splitlines()]
    assert len(lines) == 2

    # SQLite has both rows
    counts = repo.count_by_dimension()
    assert counts == {"timeliness": 2}

    # load_evidence_map prefers SQLite
    evidence = load_evidence_map(evidence_dir)
    assert "timeliness" in evidence
    principles = evidence["timeliness"]["principles"]
    assert "P1" in principles and "P2" in principles
