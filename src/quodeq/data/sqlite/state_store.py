from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite._row_mappers import judgment_to_row

_logger = logging.getLogger(__name__)
_CHECKPOINT_KEY = "projection_checkpoint"
_PROJECTED_SIZE_KEY = "projection_event_log_size"
_ACTIONS_SIZE_KEY = "actions_log_projected_size"

_INSERT_FINDING = """
INSERT OR IGNORE INTO findings (
    schema_version, practice_id, dimension, requirement, verdict, severity,
    file, line, end_line, title, reason, snippet, violation_type, context,
    scope, req_refs_json, dedup_key, confidence
) VALUES (
    :schema_version, :practice_id, :dimension, :requirement, :verdict, :severity,
    :file, :line, :end_line, :title, :reason, :snippet, :violation_type, :context,
    :scope, :req_refs_json, :dedup_key, :confidence
)
"""


class SQLiteStateStore:
    """Writes projected event state into evaluation.db."""

    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def record_finding(self, payload: Judgment) -> None:
        row = judgment_to_row(payload)
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(_INSERT_FINDING, row)
            conn.commit()

    def clear_all(self) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute("DELETE FROM findings")
            conn.execute("DELETE FROM dimension_scores")
            conn.execute(
                "DELETE FROM run_meta WHERE key IN (?, ?, ?)",
                (_CHECKPOINT_KEY, _PROJECTED_SIZE_KEY, _ACTIONS_SIZE_KEY),
            )
            conn.commit()

    def get_checkpoint(self) -> Optional[datetime]:
        with open_evaluation_db(self._run_dir) as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_CHECKPOINT_KEY,)
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0])

    def save_checkpoint(self, ts: datetime) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_CHECKPOINT_KEY, ts.isoformat()),
            )
            conn.commit()

    def get_projected_size(self) -> int | None:
        with open_evaluation_db(self._run_dir) as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_PROJECTED_SIZE_KEY,)
            ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def save_projected_size(self, size: int) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_PROJECTED_SIZE_KEY, str(size)),
            )
            conn.commit()

    def update_verdict(self, *, req: str, file: str, line: int, verdict: str) -> int:
        """Update a finding's verdict by (requirement, file, line). Returns row count."""
        with open_evaluation_db(self._run_dir) as conn:
            cur = conn.execute(
                "UPDATE findings SET verdict = ? "
                "WHERE requirement = ? AND file = ? AND line = ?",
                (verdict, req, file, line),
            )
            conn.commit()
            return cur.rowcount

    def get_actions_projected_size(self) -> int | None:
        with open_evaluation_db(self._run_dir) as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_ACTIONS_SIZE_KEY,)
            ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def save_actions_projected_size(self, size: int) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_ACTIONS_SIZE_KEY, str(size)),
            )
            conn.commit()

    # --- grade tables -----------------------------------------------------

    def record_dimension_score(
        self, *, dimension: str, score: float | None, grade: str | None,
    ) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(
                "INSERT INTO dimension_scores (dimension, score, grade, completed_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(dimension) DO UPDATE SET "
                "score=excluded.score, grade=excluded.grade, completed_at=excluded.completed_at",
                (dimension, score, grade),
            )
            conn.commit()

    def record_principle_grade(
        self, *,
        dimension: str,
        principle_id: str,
        score: float | None,
        grade: str | None,
        finding_count: int,
        dismissed_count: int,
    ) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(
                "INSERT INTO principle_grades "
                "(dimension, principle_id, score, grade, finding_count, dismissed_count, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now')) "
                "ON CONFLICT(dimension, principle_id) DO UPDATE SET "
                "score=excluded.score, grade=excluded.grade, "
                "finding_count=excluded.finding_count, dismissed_count=excluded.dismissed_count, "
                "completed_at=excluded.completed_at",
                (dimension, principle_id, score, grade, finding_count, dismissed_count),
            )
            conn.commit()

    def clear_grades(self) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute("DELETE FROM dimension_scores")
            conn.execute("DELETE FROM principle_grades")
            conn.commit()

    def read_dimension_scores(self) -> list[dict]:
        with open_evaluation_db(self._run_dir) as conn:
            rows = conn.execute(
                "SELECT dimension, score, grade FROM dimension_scores ORDER BY dimension"
            ).fetchall()
        return [{"dimension": r[0], "score": r[1], "grade": r[2]} for r in rows]

    def read_principle_grades(self) -> list[dict]:
        with open_evaluation_db(self._run_dir) as conn:
            rows = conn.execute(
                "SELECT dimension, principle_id, score, grade, finding_count, dismissed_count "
                "FROM principle_grades ORDER BY dimension, principle_id"
            ).fetchall()
        return [
            {
                "dimension": r[0], "principle_id": r[1], "score": r[2], "grade": r[3],
                "finding_count": r[4], "dismissed_count": r[5],
            }
            for r in rows
        ]

    def read_run_score_from_dim_scores(self) -> dict:
        """Compute run-level score as the mean of non-null dimension scores."""
        from quodeq.core.scoring.internals import score_to_grade_label  # noqa: PLC0415
        rows = self.read_dimension_scores()
        scores = [r["score"] for r in rows if r["score"] is not None]
        if not scores:
            return {"score": None, "grade": None}
        avg = round(sum(scores) / len(scores), 1)
        return {"score": avg, "grade": score_to_grade_label(avg)}
