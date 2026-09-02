from __future__ import annotations

from datetime import datetime
from typing import Optional

_CHECKPOINT_KEY = "projection_checkpoint"
_PROJECTED_SIZE_KEY = "projection_event_log_size"
_ACTIONS_SIZE_KEY = "actions_log_projected_size"
_GRADES_ALGO_KEY = "grades_algo_version"


class _StateStoreMetaMixin:
    """Checkpoint / projected-size / grades-algo run_meta get+save pairs.

    Split out of ``SQLiteStateStore`` purely to keep that file under the
    size cap; these methods rely on ``self._db()`` provided by the class
    they are mixed into.
    """

    def get_checkpoint(self) -> Optional[datetime]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_CHECKPOINT_KEY,)
            ).fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(row[0])

    def save_checkpoint(self, ts: datetime) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_CHECKPOINT_KEY, ts.isoformat()),
            )
            conn.commit()

    def get_projected_size(self) -> int | None:
        with self._db() as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_PROJECTED_SIZE_KEY,)
            ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def save_projected_size(self, size: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_PROJECTED_SIZE_KEY, str(size)),
            )
            conn.commit()

    def get_actions_projected_size(self) -> int | None:
        with self._db() as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_ACTIONS_SIZE_KEY,)
            ).fetchone()
        if row is None:
            return None
        return int(row[0])

    def save_actions_projected_size(self, size: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_ACTIONS_SIZE_KEY, str(size)),
            )
            conn.commit()

    def get_grades_algo_version(self) -> int | None:
        """Version of the grade math the stored grade tables were computed with.

        None means the tables predate the stamp (or were never computed);
        callers treat that as stale so pre-stamp DBs heal on first contact.
        """
        with self._db() as conn:
            row = conn.execute(
                "SELECT value FROM run_meta WHERE key = ?", (_GRADES_ALGO_KEY,)
            ).fetchone()
        if row is None:
            return None
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return None

    def save_grades_algo_version(self, version: int) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)",
                (_GRADES_ALGO_KEY, str(version)),
            )
            conn.commit()
