"""Builder for the `runs` UI data unit.

Assembles one project's run list from the SQLite run index (status + dates)
plus per-dimension scalar scores from the score cache. Returns camelCase dicts
sized for History rows, the trend chart, and the run navigator — NOT the
multi-MB dashboard payload.
"""
from __future__ import annotations

from quodeq.services.run_index import RunRow

_INDEX_STATE_TO_UI_STATUS = {
    "done": "complete", "complete": "complete", "finished": "complete",
    "running": "in_progress", "in_progress": "in_progress",
    "cancelled": "cancelled", "canceled": "cancelled",
    "failed": "failed", "error": "failed",
}


def _ui_status(state: str) -> str:
    """Map an index `state` to the UI's run status vocabulary."""
    return _INDEX_STATE_TO_UI_STATUS.get((state or "").lower(), "complete")


def _row_to_run_entry(row: RunRow) -> dict:
    """One index row → a runs-unit entry with score placeholders."""
    return {
        "runId": row.run_id,
        "status": _ui_status(row.state),
        "dateISO": row.started_at,
        "overallScore": None,
        "overallGrade": None,
        "dimensionScores": {},
    }
