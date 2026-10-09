from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Optional, TypeVar

_CHECKPOINT_KEY = "projection_checkpoint"
_PROJECTED_SIZE_KEY = "projection_event_log_size"
_ACTIONS_SIZE_KEY = "actions_log_projected_size"
_GRADES_ALGO_KEY = "grades_algo_version"
_GRADES_CLASSES_KEY = "grades_severity_classes"
_COVERAGE_STAMP_KEY = "coverage_report_stamp"
_MAPPING_STAMPS_KEY = "standard_mapping_stamps"

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

    def get_grades_classes_fingerprint(self) -> str | None:
        """Fingerprint of the severity classes the stored grade tables were
        computed with; None when the tables predate it (read as stale)."""
        return self._get_meta(_GRADES_CLASSES_KEY, str)

    def save_grades_classes_fingerprint(self, fingerprint: str) -> None:
        self._save_meta(_GRADES_CLASSES_KEY, fingerprint)

    def get_coverage_stamp(self) -> str | None:
        """Report stamp (newest ``evaluation/*.json`` mtime) the coverage columns
        were read from; None when the tables predate the stamp."""
        return self._get_meta(_COVERAGE_STAMP_KEY, str)

    def save_coverage_stamp(self, stamp: str) -> None:
        self._save_meta(_COVERAGE_STAMP_KEY, stamp)

    def get_mapping_stamps(self) -> dict[str, str] | None:
        """``{dimension: mapping stamp}`` of the standards the findings were placed
        with; None when the run was projected before stamps existed."""
        stamps = self._get_meta(_MAPPING_STAMPS_KEY, json.loads)
        return stamps if isinstance(stamps, dict) else None

    def save_mapping_stamps(self, stamps: dict[str, str]) -> None:
        self._save_meta(_MAPPING_STAMPS_KEY, json.dumps(stamps, sort_keys=True))
