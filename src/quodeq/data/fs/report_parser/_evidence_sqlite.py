"""Build the load_evidence_map() dict shape from evaluation.db.

Mirrors the legacy `_evidence.json` shape so callers downstream
(parse_jsonl_to_evidence, scoring engine, CI reader) see the same dict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def has_evaluation_db(run_dir: Path) -> bool:
    return (run_dir / EVALUATION_DB_FILENAME).is_file()


def load_evidence_map_from_db(run_dir: Path) -> dict[str, dict[str, Any]]:
    repo = SqliteFindingsRepository(run_dir)
    counts = repo.count_by_dimension()
    result: dict[str, dict[str, Any]] = {}
    for dimension in counts:
        judgments = repo.list_by_dimension(dimension)
        violations = [_judgment_to_finding_dict(j) for j in judgments if j.verdict == "violation"]
        compliance = [_judgment_to_finding_dict(j) for j in judgments if j.verdict == "compliance"]
        principles: dict[str, dict[str, Any]] = {}
        for j in judgments:
            entry = principles.setdefault(j.practice_id, {
                "display_name": j.practice_id,
                "violations": [],
                "compliance": [],
            })
            target = entry["violations"] if j.verdict == "violation" else entry["compliance"]
            target.append(_judgment_to_finding_dict(j))
        result[dimension] = {
            "dimension": dimension,
            "principles": principles,
            "violation_count": len(violations),
            "compliance_count": len(compliance),
        }
    return result


def _judgment_to_finding_dict(j) -> dict[str, Any]:
    return {
        "practice_id": j.practice_id,
        "file": j.file,
        "line": j.line,
        "end_line": j.end_line,
        "snippet": j.snippet,
        "verdict": j.verdict,
        "severity": j.severity,
        "reason": j.reason,
        "title": j.title,
        "req": j.req,
        "req_refs": j.req_refs,
    }
