"""A small multi-run project and an I/O counter for the request budgets."""
from __future__ import annotations

import builtins
import io
import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector

PROJECT = "proj"
LATEST_ONLY = {"req": "S-INT-3", "file": "f10.py", "line": 20}  # only in the newest run
RUNS = 6
VIOLATIONS_PER_RUN = 6


# Real security requirements, so projection places them as it does in use.
_REQS = [(f"S-CON-{n}", "Confidentiality") for n in range(1, 9)] + [
    (f"S-INT-{n}", "Integrity") for n in range(1, 4)]


def _violation(i: int) -> dict:
    req, principle = _REQS[i]
    return dict(
        practice_id=principle, verdict="violation", dimension="security",
        file=f"f{i}.py", line=10 + i, reason="r", req=req, severity="high",
        snippet=f"md5(secret_{i})",
    )


FILES_READ = 40


def seed_project(reports_root: Path, name: str = PROJECT) -> Path:
    """RUNS finished runs of one project, each projected into its evaluation.db."""
    project_dir = reports_root / name
    for n in range(RUNS):
        run_dir = project_dir / f"2026010{n}T000000"
        (run_dir / "evaluation").mkdir(parents=True)
        (run_dir / "evidence").mkdir()
        (run_dir / "evidence" / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
        (run_dir / "status.json").write_text(json.dumps({"state": "done"}), encoding="utf-8")
        # Each run shifts its window by one, so older findings age out the way
        # fixed code does and the newest finding exists in the latest run only.
        violations = [_violation(i) for i in range(n, n + VIOLATIONS_PER_RUN)]
        # A real scan records the files it read; the scalar readers trust a
        # grade row only when it carries that count.
        (run_dir / "evaluation" / "security.json").write_text(json.dumps({
            "dimension": "security", "overallScore": "6.0/10", "overallGrade": "Adequate",
            "filesRead": FILES_READ, "principles": [], "compliance": [],
            "violations": [{"practiceId": v["practice_id"], "req": v["req"], "file": v["file"],
                            "line": v["line"], "severity": v["severity"], "snippet": v["snippet"]}
                           for v in violations],
            "totals": {"violationCount": len(violations), "complianceCount": 0,
                       "severity": {"critical": 0, "major": len(violations), "minor": 0}},
        }), encoding="utf-8")
        log = run_dir / "events.jsonl"
        writer = EventLogWriter(log)
        for v in violations:
            writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**v)))
        Projector().ensure_projected(log, run_dir, project_dir=project_dir)
    return project_dir


def _kind(path: str) -> str | None:
    if path.endswith("actions.jsonl"):
        return "actions_log_reads"
    if "/evaluation/" in path and path.endswith(".json"):
        return "eval_report_reads"
    if path.endswith("_evidence.jsonl") or path.endswith("_evidence.json"):
        return "evidence_reads"
    if path.endswith("events.jsonl"):
        return "event_log_reads"
    if "/standards/" in path and path.endswith(".json"):
        return "standards_reads"
    return None


@contextmanager
def count_io(monkeypatch):
    """Count file opens by kind, and evaluation.db connections, inside the block."""
    counts: Counter[str] = Counter()
    real_open, real_connect = io.open, sqlite3.connect

    def counting_open(file, mode="r", *args, **kwargs):
        if "r" in mode and (kind := _kind(str(file).replace("\\", "/"))):
            counts[kind] += 1
        return real_open(file, mode, *args, **kwargs)

    def counting_connect(database, *args, **kwargs):
        if str(database).replace("\\", "/").endswith("evaluation.db"):
            counts["evaluation_db_opens"] += 1
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(io, "open", counting_open)
    monkeypatch.setattr(builtins, "open", counting_open)
    monkeypatch.setattr(sqlite3, "connect", counting_connect)
    try:
        yield counts
    finally:
        monkeypatch.setattr(io, "open", real_open)
        monkeypatch.setattr(builtins, "open", real_open)
        monkeypatch.setattr(sqlite3, "connect", real_connect)
