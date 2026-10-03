"""Per-dimension counts of active violations and compliance from the findings table.

The scalar read path serves grades without findings; these counts let the
trend show violations, majors and open requirement types per run without
loading the findings themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.core.types.finding_type import FindingType
from quodeq.core.types.severity import Severity
from quodeq.data.sqlite._db_stamp_memo import memoized_by_db_stamp
from quodeq.shared.stamp_memo import StampCache
from quodeq.data.sqlite.connection import EVALUATION_DB_FILENAME, open_evaluation_db

_LEGACY_HIGH = "high"  # older rows spell major as high
# One scan per run: per dimension, verdict and severity, the row count and the
# distinct requirement codes among rows that carry one.
_SELECT_COUNTS = (
    "SELECT dimension, verdict, severity, COUNT(*), "
    "COUNT(DISTINCT CASE WHEN requirement IS NOT NULL AND requirement != '' THEN requirement END) "
    "FROM findings WHERE verdict IN ('violation', 'compliance') GROUP BY dimension, verdict, severity"
)
_SELECT_TYPES = (
    "SELECT dimension, COUNT(DISTINCT requirement) FROM findings "
    "WHERE verdict = 'violation' AND requirement IS NOT NULL AND requirement != '' "
    "GROUP BY dimension"
)


# Own store: the memo is keyed by database path, which other per-run reads
# (the run key sets) memoize under too.
_COUNTS_CACHE = StampCache(max_entries=512, name="dimension_counts")


@dataclass(frozen=True, slots=True)
class DimensionCounts:
    """Active violations of one dimension by severity, distinct requirement codes, and compliance."""

    critical: int = 0
    major: int = 0
    minor: int = 0
    open_types: int = 0
    compliance: int = 0

    @property
    def violations(self) -> int:
        """All active violations, whatever their severity."""
        return self.critical + self.major + self.minor


def read_dimension_counts(run_dir: Path) -> dict[str, DimensionCounts]:
    """``{dimension: DimensionCounts}`` over non-dismissed violations and compliance in *run_dir*.

    Reused while the run database is unchanged (``memoized_by_db_stamp``): the
    scores, the card summary and the trend each ask for the same run's counts.
    """
    counts = memoized_by_db_stamp(run_dir / EVALUATION_DB_FILENAME, lambda: _read_counts(run_dir),
                                  cache=_COUNTS_CACHE)
    return dict(counts) if counts is not None else _read_counts(run_dir)


def _read_counts(run_dir: Path) -> dict[str, DimensionCounts]:
    by_dim: dict[str, dict[str, int]] = {}
    with open_evaluation_db(run_dir) as conn:
        rows = conn.execute(_SELECT_COUNTS).fetchall()
        type_rows = conn.execute(_SELECT_TYPES).fetchall()
    for dimension, verdict, severity, count, _types in rows:
        bucket = by_dim.setdefault(dimension, {})
        key = FindingType.COMPLIANCE if verdict == FindingType.COMPLIANCE else _bucket_for(severity)
        bucket[key] = bucket.get(key, 0) + int(count)
    for dimension, types in type_rows:
        by_dim.setdefault(dimension, {})["open_types"] = int(types)
    return {dim: DimensionCounts(**fields) for dim, fields in by_dim.items()}


def _bucket_for(severity: str | None) -> str:
    if severity == Severity.CRITICAL:
        return "critical"
    if severity in (Severity.MAJOR, _LEGACY_HIGH):
        return "major"
    return "minor"
