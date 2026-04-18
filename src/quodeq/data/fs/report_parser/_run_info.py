"""Run metadata types and directory-scanning helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from quodeq.data.fs.report_parser._date_utils import find_date_in_dir, normalize_date
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunInfo:
    """Metadata for a single evaluation run (ID and date information)."""

    run_id: str
    date_iso: str | None
    date_label: str
    branch: str | None = None
    scope_path: str | None = None
    status: str = "complete"  # "complete" | "in_progress"


def safe_read_dir(path: Path) -> list[os.DirEntry[str]]:
    """List directory entries, returning an empty list on OS errors.

    Materializes entries via scandir into a list.  This is intentional:
    callers iterate entries multiple times (e.g. markdown-backed pass then
    JSON-only pass in ``_evaluations.py``) and the entry count per directory
    is small, so full materialization is the correct trade-off here.

    Example::

        entries = safe_read_dir(Path("/data/reports"))
    """
    try:
        return list(os.scandir(path))
    except OSError as exc:
        _logger.debug(
            "Could not list directory %s: %s. Check path exists and file permissions are correct",
            path.name,
            exc,
        )
        return []


def parse_run_date(reports_root: Path, project: str, run_id: str) -> tuple[str | None, str]:
    """Read the date from evidence or evaluation files in a run directory."""
    validate_path_segment(project, run_id)
    run_dir = reports_root / project / run_id

    result = find_date_in_dir(run_dir / "evidence", "_evidence.json", safe_read_dir)
    if result:
        return result

    result = find_date_in_dir(run_dir / "evaluation", ".json", safe_read_dir)
    if result:
        return result

    fallback = normalize_date(run_id)
    if fallback:
        return fallback
    return None, run_id
