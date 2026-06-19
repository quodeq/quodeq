"""Build the load_evidence_map() dict shape from evaluation.db.

Mirrors the legacy `_evidence.json` shape so callers downstream
(parse_jsonl_to_evidence, scoring engine, CI reader) see the same dict.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.core.finding_mappings import finding_to_response_dict
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
    # Fetch all findings in one query, then group by dimension in Python.
    # Previously this called count_by_dimension() + list_by_dimension(dim)
    # for each dimension, which was an N+1 query pattern.
    all_judgments = repo.list_all()
    run_metadata = _load_run_metadata(run_dir)
    result: dict[str, dict[str, Any]] = {}
    for j in all_judgments:
        dimension = j.dimension
        if dimension not in result:
            result[dimension] = {
                "dimension": dimension,
                "principles": {},
                "violation_count": 0,
                "compliance_count": 0,
                "sourceFileCount": run_metadata["sourceFileCount"],
                "date": run_metadata["date"],
                "discipline": run_metadata["discipline"],
            }
        entry = result[dimension]["principles"].setdefault(j.practice_id, {
            "display_name": j.practice_id,
            "violations": [],
            "compliance": [],
        })
        finding_dict = finding_to_response_dict(j)
        if j.verdict == "violation":
            entry["violations"].append(finding_dict)
            result[dimension]["violation_count"] += 1
        elif j.verdict == "compliance":
            entry["compliance"].append(finding_dict)
            result[dimension]["compliance_count"] += 1
        else:
            # "dismissed" (and any future verdict) goes into compliance list for
            # display purposes (matching the old per-dimension behaviour) but
            # must NOT increment compliance_count — the old code derived counts
            # via len([j for j in judgments if j.verdict == "compliance"]).
            entry["compliance"].append(finding_dict)
    return result
