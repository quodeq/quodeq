from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quodeq.core.events.models import JudgmentPayload
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite._row_mappers import finding_payload_to_row

_logger = logging.getLogger(__name__)
_CHECKPOINT_KEY = "projection_checkpoint"

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

    def record_finding(self, payload: JudgmentPayload) -> None:
        row = finding_payload_to_row(payload)
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute(_INSERT_FINDING, row)
            conn.commit()

    def clear_all(self) -> None:
        with open_evaluation_db(self._run_dir) as conn:
            conn.execute("DELETE FROM findings")
            conn.execute("DELETE FROM dimension_scores")
            conn.execute(
                "DELETE FROM run_meta WHERE key = ?", (_CHECKPOINT_KEY,)
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
