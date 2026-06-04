"""Evidence file loading from run directories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser._evidence_sqlite import (
    has_evaluation_db,
    load_evidence_map_from_db,
)
from quodeq.data.fs.report_parser._run_info import safe_read_dir
from quodeq.data.fs.report_parser.json_parser import parse_evidence_file
from quodeq.shared._env import sqlite_disabled

_logger = logging.getLogger(__name__)


def _load_evidence_from_dir(directory: Path, module: str = "") -> dict[str, dict[str, Any]]:
    """Load evidence files from a single directory, keyed by dimension name."""
    evidence_map: dict[str, dict[str, Any]] = {}
    for entry in safe_read_dir(directory):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            parsed_ev = parse_evidence_file(Path(entry.path))
            dimension = parsed_ev.get("dimension")
            if dimension is None:
                _logger.warning(
                    "Evidence file %s missing 'dimension' key, skipping", entry.name,
                )
                continue
            if module:
                parsed_ev["module"] = module
            evidence_map[dimension] = parsed_ev
    return evidence_map


def load_evidence_map(evidence_dir: Path) -> dict[str, dict[str, Any]]:
    """Load evidence files keyed by dimension name.

    Prefers SQLite (evaluation.db in the run directory) when available;
    falls back to per-dimension `_evidence.json` files for legacy runs.
    """
    run_dir = evidence_dir.parent
    if not sqlite_disabled() and has_evaluation_db(run_dir):
        import sqlite3  # noqa: PLC0415
        try:
            return load_evidence_map_from_db(run_dir)
        except sqlite3.DatabaseError:
            # evaluation.db is unreadable by this binary: written by a newer
            # Quodeq (SchemaVersionError, a DatabaseError subclass) or otherwise
            # corrupt/half-written. Don't crash the run read; fall back to the
            # per-dimension _evidence.json files below.
            _logger.warning(
                "evaluation.db at %s is unreadable; falling back to "
                "_evidence.json files", run_dir,
            )

    evidence_map = _load_evidence_from_dir(evidence_dir)
    for entry in safe_read_dir(evidence_dir):
        if entry.is_dir() and not entry.name.startswith("."):
            sub_map = _load_evidence_from_dir(evidence_dir / entry.name, module=entry.name)
            evidence_map.update(sub_map)
    return evidence_map
