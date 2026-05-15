"""Build the load_evidence_map() dict shape from evaluation.db.

Mirrors the legacy `_evidence.json` shape so callers downstream
(parse_jsonl_to_evidence, scoring engine, CI reader) see the same dict.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser._date_utils import find_date_in_dir, normalize_date
from quodeq.data.fs.report_parser._run_info import safe_read_dir
from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)


def has_evaluation_db(run_dir: Path) -> bool:
    return (run_dir / EVALUATION_DB_FILENAME).is_file()


def _load_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Read run-level metadata (sourceFileCount, date, discipline) shared by all dimensions.

    Pulls source-file count and language from ``evidence/manifest.json`` (the
    canonical run-level manifest), and falls back to scanning evaluation JSON
    files or parsing the run-id for the date.  Any missing field is left as
    ``None`` so callers receive a stable shape.
    """
    metadata: dict[str, Any] = {
        "sourceFileCount": None,
        "date": None,
        "discipline": None,
    }

    manifest_path = run_dir / "evidence" / "manifest.json"
    if manifest_path.is_file():
        try:
            data = read_json(manifest_path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            _logger.warning("Failed to read run manifest %s: %s", manifest_path, exc)
            data = {}
        if isinstance(data, dict):
            sfc = data.get("source_files_count")
            if isinstance(sfc, int):
                metadata["sourceFileCount"] = sfc
            language = data.get("language")
            if isinstance(language, str) and language:
                metadata["discipline"] = language

    # Date precedence:
    #   (a) any evaluation/<dim>.json carrying a parsable "date"
    #   (b) the run directory name (e.g. "20260301" or "2026-03-01T14:30:25")
    #   (c) None
    eval_date = find_date_in_dir(run_dir / "evaluation", ".json", safe_read_dir)
    if eval_date:
        metadata["date"] = eval_date[0]
    else:
        normalized = normalize_date(run_dir.name)
        if normalized:
            metadata["date"] = normalized[0]

    return metadata


def load_evidence_map_from_db(run_dir: Path) -> dict[str, dict[str, Any]]:
    repo = SqliteFindingsRepository(run_dir)
    counts = repo.count_by_dimension()
    run_metadata = _load_run_metadata(run_dir)
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
            "sourceFileCount": run_metadata["sourceFileCount"],
            "date": run_metadata["date"],
            "discipline": run_metadata["discipline"],
        }
    return result


def _judgment_to_finding_dict(j) -> dict[str, Any]:
    req_refs = [{"label": r.label, "url": r.url} for r in j.req_refs] if j.req_refs else None
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
        "req_refs": req_refs,
    }
