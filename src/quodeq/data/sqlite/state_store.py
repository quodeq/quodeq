from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from quodeq.core.scoring.params import ScoringParams

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
    scope, req_refs_json, dedup_key, confidence, provenance_downgrade
) VALUES (
    :schema_version, :practice_id, :dimension, :requirement, :verdict, :severity,
    :file, :line, :end_line, :title, :reason, :snippet, :violation_type, :context,
    :scope, :req_refs_json, :dedup_key, :confidence, :provenance_downgrade
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
        """Update a finding's verdict by (requirement, file, line). Returns row count.

        A finding with no requirement id is stored with ``requirement`` NULL, but
        the dismiss/restore event carries an empty string. ``requirement = ''``
        never matches NULL in SQL, so an empty ``req`` is matched on (file, line)
        against rows whose requirement is NULL or empty, scoped so it cannot
        sweep a different, req-bearing finding at the same location.
        """
        with open_evaluation_db(self._run_dir) as conn:
            if req:
                cur = conn.execute(
                    "UPDATE findings SET verdict = ? "
                    "WHERE requirement = ? AND file = ? AND line = ?",
                    (verdict, req, file, line),
                )
            else:
                cur = conn.execute(
                    "UPDATE findings SET verdict = ? "
                    "WHERE (requirement IS NULL OR requirement = '') "
                    "AND file = ? AND line = ?",
                    (verdict, file, line),
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

    def batch_rewrite_grades(
        self,
        principle_rows: "list[tuple[str, dict]]",
        dimension_rows: "list[dict]",
    ) -> None:
        """Clear all grade tables and insert new rows in a single transaction.

        The clear + all inserts are committed atomically: on a mid-batch
        failure the transaction is never committed and is discarded when the
        connection closes, leaving any pre-existing rows intact.

        Args:
            principle_rows: Sequence of ``(dimension, principle_grade_dict)``
                as returned by ``compute_run_grades``.
            dimension_rows: Sequence of dimension score dicts
                (``{"dimension": ..., "score": ..., "grade": ...}``).
        """
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute("DELETE FROM dimension_scores")
            conn.execute("DELETE FROM principle_grades")
            for dim, p_grade in principle_rows:
                conn.execute(
                    "INSERT INTO principle_grades "
                    "(dimension, principle_id, score, grade, finding_count, dismissed_count, completed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                    (
                        dim,
                        p_grade["principle_id"],
                        p_grade["score"],
                        p_grade["grade"],
                        p_grade["finding_count"],
                        p_grade["dismissed_count"],
                    ),
                )
            for d_score in dimension_rows:
                conn.execute(
                    "INSERT INTO dimension_scores (dimension, score, grade, completed_at) "
                    "VALUES (?, ?, ?, datetime('now'))",
                    (d_score["dimension"], d_score["score"], d_score["grade"]),
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

    def read_run_score_from_dim_scores(self, params: "ScoringParams | None" = None) -> dict:
        """Compute the run-level score from non-null dimension scores (weighted when params enable dimension weights)."""
        from quodeq.services.scoring.projector_scoring import compute_run_score  # noqa: PLC0415
        from quodeq.core.scoring.params import DEFAULT_PARAMS  # noqa: PLC0415
        rows = self.read_dimension_scores()
        return compute_run_score(rows, params=params if params is not None else DEFAULT_PARAMS)
