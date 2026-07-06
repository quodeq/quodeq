# src/quodeq/services/run_dates.py
"""Index-backed run-date resolution for fast enumeration.

`list_runs` otherwise reads a JSON file per run just to get its date. The run
index already stores each run's ``started_at`` (which equals the displayed
date), so this returns a ``{run_id: (date_iso, date_label)}`` map from the index,
refreshing it with a cheap mtime-gated per-project sync first. Best-effort: any
index error yields ``{}`` and the caller falls back to ``parse_run_date``.
"""
from __future__ import annotations

import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def project_run_dates(reports_root: Path, project: str) -> dict[str, tuple[str, str]]:
    """Return ``{run_id: (date_iso, date_label)}`` from the run index, or ``{}``."""
    try:
        from quodeq.data.fs.report_parser._date_utils import normalize_date  # noqa: PLC0415
        from quodeq.services.run_index import (  # noqa: PLC0415
            list_runs_for_project, open_index, sync_project_dates,
        )
        from quodeq.shared._env import get_index_db_path  # noqa: PLC0415

        db = open_index(Path(get_index_db_path()))
        try:
            sync_project_dates(db, Path(reports_root) / project, project)
            rows = list_runs_for_project(db, project)
        finally:
            db.close()
    except Exception:
        _logger.debug("project_run_dates: index unavailable for %s", project, exc_info=True)
        return {}

    out: dict[str, tuple[str, str]] = {}
    for r in rows:
        if not r.started_at:
            continue
        normalized = normalize_date(r.started_at)
        if normalized:
            out[r.run_id] = normalized
    return out
