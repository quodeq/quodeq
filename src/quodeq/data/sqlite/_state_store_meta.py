from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional, TypeVar

_CHECKPOINT_KEY = "projection_checkpoint"
_PROJECTED_SIZE_KEY = "projection_event_log_size"
_ACTIONS_SIZE_KEY = "actions_log_projected_size"
_GRADES_ALGO_KEY = "grades_algo_version"

T = TypeVar("T")


class StateStoreMetaMixin:
    """Typed get/save pairs over the run_meta key/value table.

    Split out of ``SQLiteStateStore`` purely to keep that file under the
    size cap; these methods rely on ``self._db()`` provided by the class
    they are mixed into.
    """

    def _get_meta(self, key: str, cast: Callable[[str], T]) -> T | None:
        """Read one run_meta value through *cast*; None when missing or malformed."""
        with self._db() as conn:
            row = conn.execute("SELECT value FROM run_meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            return cast(row[0])
        except (TypeError, ValueError):
            return None

    def _save_meta(self, key: str, value: str) -> None:
        with self._db() as conn:
            conn.execute("INSERT OR REPLACE INTO run_meta (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    def get_checkpoint(self) -> Optional[datetime]:
        return self._get_meta(_CHECKPOINT_KEY, datetime.fromisoformat)

    def save_checkpoint(self, ts: datetime) -> None:
        self._save_meta(_CHECKPOINT_KEY, ts.isoformat())

    def get_projected_size(self) -> int | None:
        return self._get_meta(_PROJECTED_SIZE_KEY, int)

    def save_projected_size(self, size: int) -> None:
        self._save_meta(_PROJECTED_SIZE_KEY, str(size))

    def get_actions_projected_size(self) -> int | None:
        return self._get_meta(_ACTIONS_SIZE_KEY, int)

    def save_actions_projected_size(self, size: int) -> None:
        self._save_meta(_ACTIONS_SIZE_KEY, str(size))

    def get_grades_algo_version(self) -> int | None:
        """Version of the grade math the stored grade tables were computed with.

        None means the tables predate the stamp (or were never computed);
        callers treat that as stale so pre-stamp DBs heal on first contact.
        """
        return self._get_meta(_GRADES_ALGO_KEY, int)

    def save_grades_algo_version(self, version: int) -> None:
        self._save_meta(_GRADES_ALGO_KEY, str(version))
