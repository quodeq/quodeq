"""Builder for the `runs` UI data unit.

Assembles one project's run list from the SQLite run index (status + dates)
plus per-dimension scalar scores from the score cache. Returns camelCase dicts
sized for History rows, the trend chart, and the run navigator — NOT the
multi-MB dashboard payload.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.core.run.state import ACTIVE_STATES, TERMINAL_STATES, RunState, parse_run_state
from quodeq.core.scoring.report_grades import most_frequent_grade, parse_numeric_score
from quodeq.services.wiring import (
    RunRow,
    list_runs_for_project,
    open_index,
    read_run_scalars,
    sync_index,
)

_log = logging.getLogger(__name__)


def _row_status(state: str) -> RunState:
    """The run-list status an index row means: a terminal state, or RUNNING for any live one.

    The runs endpoint collapses every ACTIVE_STATES member to RUNNING; the UI
    has no pending/finalizing row state. Unknown spellings read as DONE, logged.
    """
    try:
        s = parse_run_state(state)
    except ValueError:
        _log.warning("index row with unknown state %r read as done", state)
        return RunState.DONE
    return RunState.RUNNING if s in ACTIVE_STATES else s


def _row_to_run_entry(row: RunRow) -> dict:
    """One index row → a runs-unit entry with score placeholders."""
    return {
        "runId": row.run_id,
        "status": _row_status(row.state),
        "dateISO": row.started_at,
        "overallScore": None,
        "overallGrade": None,
        "dimensionScores": {},
    }


def _fill_scores(entry: dict, reports_root: Path, project: str, run_id: str) -> None:
    """Populate dimensionScores/overallScore/overallGrade in place.

    Terminal runs only; failures leave placeholders untouched. read_run_scalars
    is score-cache backed for terminal runs, so this is cheap. DimensionResult
    carries overall_score as a string ("7.5/10"); parse_numeric_score turns it
    into a float, matching every production caller (see dashboard_trend.py).
    """
    if entry["status"] not in TERMINAL_STATES:
        return
    try:
        dims = read_run_scalars(reports_root, project, run_id)
    except (OSError, ValueError):
        return
    scores = {}
    for d in dims:
        raw = getattr(d, "overall_score", None)
        s = parse_numeric_score(raw) if raw else None
        if s is not None:
            scores[d.dimension] = s
    if not scores:
        return
    entry["dimensionScores"] = scores
    entry["overallScore"] = round(sum(scores.values()) / len(scores), 1)
    grades = [d.overall_grade for d in dims if getattr(d, "overall_grade", None)]
    entry["overallGrade"] = most_frequent_grade(grades) if grades else None


def build_runs_unit(reports_root: Path, index_db_path: Path, project: str) -> list[dict]:
    """Assemble the `runs` unit for one project.

    Status + dates from the index (synced first so freshly-written runs appear);
    scalar scores from the score cache.
    """
    db = open_index(index_db_path)
    try:
        sync_index(db, reports_root)
        rows = list_runs_for_project(db, project, limit=None)
    finally:
        db.close()
    entries = [_row_to_run_entry(r) for r in rows]
    for entry in entries:
        _fill_scores(entry, reports_root, project, entry["runId"])
    return entries
