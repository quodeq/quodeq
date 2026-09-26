"""Per-dimension counts of active violations from the findings table.

The scalar read path serves grades without findings; these counts let the
trend show violations, majors and open requirement types per run without
loading the findings themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.core.types.severity import Severity
from quodeq.data.sqlite.connection import open_evaluation_db

_LEGACY_HIGH = "high"  # older rows spell major as high
_SELECT_COUNTS = (
    "SELECT dimension, severity, COUNT(*), COUNT(DISTINCT requirement) "
    "FROM findings WHERE verdict = 'violation' GROUP BY dimension, severity"
)
_SELECT_TYPES = (
    "SELECT dimension, COUNT(DISTINCT requirement) FROM findings "
    "WHERE verdict = 'violation' AND requirement IS NOT NULL AND requirement != '' "
    "GROUP BY dimension"
)


@dataclass(frozen=True, slots=True)
class DimensionCounts:
    """Active violations of one dimension by severity, plus distinct requirement codes."""

    critical: int = 0
    major: int = 0
    minor: int = 0
    open_types: int = 0

    @property
    def violations(self) -> int:
        """All active violations, whatever their severity."""
        return self.critical + self.major + self.minor


def read_dimension_counts(run_dir: Path) -> dict[str, DimensionCounts]:
    """``{dimension: DimensionCounts}`` over non-dismissed violations in *run_dir*."""
    by_dim: dict[str, dict[str, int]] = {}
    with open_evaluation_db(run_dir) as conn:
        severity_rows = conn.execute(_SELECT_COUNTS).fetchall()
        type_rows = conn.execute(_SELECT_TYPES).fetchall()
    for dimension, severity, count, _types in severity_rows:
        bucket = by_dim.setdefault(dimension, {})
        key = _bucket_for(severity)
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
