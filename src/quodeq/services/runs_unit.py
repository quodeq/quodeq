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
    evaluation_db_stamp,
    list_runs_for_project,
    open_index,
    read_run_scalars,
    sync_index,
)
from quodeq.shared.stamp_memo import StampCache, file_stamp, memoized_by_stamp

_log = logging.getLogger(__name__)

_SCALARS_CACHE = StampCache(name="run_list_scalars")


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

    Terminal runs only; failures leave placeholders untouched. A terminal
    run's files no longer change, so its scalars are memoized on their stamps
    (:func:`_terminal_run_scalars`). DimensionResult carries overall_score as
    a string ("7.5/10"); parse_numeric_score turns it into a float, matching
    every production caller (see dashboard_trend.py).
    """
    if entry["status"] not in TERMINAL_STATES:
        return
    try:
        dims = _terminal_run_scalars(reports_root, project, run_id)
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


def _terminal_run_scalars(reports_root: Path, project: str, run_id: str) -> list:
    """``read_run_scalars`` for a terminal run, reused while the run's files are unchanged.

    The stamp covers everything the reader consults: the database (grade
    tables), ``events.jsonl`` (folded into it by ``ensure_projected``) and the
    ``evaluation`` directory (the per-dimension JSON the fallback parses and
    the SQL path counts). A run with none of these is read directly.
    """
    run_dir = reports_root / project / run_id
    stamp = (
        evaluation_db_stamp(run_dir),
        file_stamp(run_dir / "events.jsonl"),
        file_stamp(run_dir / "evaluation"),
    )
    if all(part is None for part in stamp):
        return read_run_scalars(reports_root, project, run_id)
    hit = memoized_by_stamp(
        str(run_dir), stamp,
        lambda: read_run_scalars(reports_root, project, run_id),
        cache=_SCALARS_CACHE,
    )
    return hit if hit is not None else []


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
