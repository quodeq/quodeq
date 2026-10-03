# src/quodeq/services/run_dates.py
"""Index-backed run-date resolution for fast enumeration.

`list_runs` otherwise reads a JSON file per run just to get its date. The run
index already stores each run's ``started_at`` (which equals the displayed
date), so this returns a ``{run_id: (date_iso, date_label)}`` map from the index,
refreshing it with a cheap mtime-gated per-project sync first. Best-effort: any
index error yields ``{}`` and the caller falls back to ``parse_run_date``.

Precedence note: for a run that has a ``status.json``, this uses ``started_at``
as the date, which intentionally supersedes ``parse_run_date``'s evidence/eval
``date``-field-first ordering. In practice the two are captured seconds apart in
the same run, so the displayed label is identical; ``started_at`` is the
canonical run timestamp and does not drift if an evidence file is later
rewritten. Runs without a usable ``started_at`` come from the ``run_dates``
table, which ``remember_run_dates`` fills with what the caller's
``parse_run_date`` fallback resolved, so that file read is paid once per run.
A finished run that has no date anywhere is remembered as undated too;
``remembered_run_dates`` includes those, ``project_run_dates`` does not.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from quodeq.data.fs.report_parser._date_utils import normalize_date
from quodeq.data.sqlite.run_index import (
    list_runs_for_project,
    open_index,
    read_run_dates,
    sync_project_dates,
    write_run_dates,
)
from quodeq.shared.env import get_index_db_path

_logger = logging.getLogger(__name__)


def project_run_dates(reports_root: Path, project: str) -> dict[str, tuple[str, str]]:
    """Return ``{run_id: (date_iso, date_label)}`` for the dated runs in the index, or ``{}``."""
    return {rid: (iso, label) for rid, (iso, label) in remembered_run_dates(reports_root, project).items()
            if iso is not None}


def remembered_run_dates(reports_root: Path, project: str) -> dict[str, tuple[str | None, str]]:
    """Every run the index knows a date for, plus the finished runs remembered as undated.

    ``{run_id: (date_iso, date_label)}``; ``date_iso`` is None for an undated
    run. ``{}`` when the index is unavailable.
    """
    try:
        db = open_index(Path(get_index_db_path()))
        try:
            sync_project_dates(db, Path(reports_root) / project, project)
            rows = list_runs_for_project(db, project, limit=None)
            remembered = read_run_dates(db, project)
        finally:
            db.close()
    except (sqlite3.Error, OSError):
        _logger.warning("project_run_dates: index unavailable for %s", project, exc_info=True)
        return {}

    out: dict[str, tuple[str | None, str]] = dict(remembered)
    for r in rows:
        if not r.started_at:
            continue
        normalized = normalize_date(r.started_at)
        if normalized:
            out[r.run_id] = normalized
    return out


def remember_run_dates(project: str, dates: dict[str, tuple[str | None, str]]) -> None:
    """Store the dates ``parse_run_date`` resolved for *project*'s runs; best-effort."""
    if not dates:
        return
    try:
        db = open_index(Path(get_index_db_path()))
        try:
            write_run_dates(db, project, dates)
        finally:
            db.close()
    except (sqlite3.Error, OSError):
        _logger.warning("remember_run_dates: index unavailable for %s", project, exc_info=True)
