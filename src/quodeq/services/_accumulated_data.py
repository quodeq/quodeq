"""Data loading helpers for the accumulated (cross-run) view."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from quodeq.services.ports import RunInfo, read_run_data
from quodeq.core.types import DimensionResult


@dataclass
class _DimensionBuckets:
    """Mutable accumulation buckets used during a single _read_all_run_data pass."""
    latest_by_dimension: dict[str, DimensionResult] = field(default_factory=dict)
    prev_occurrence: dict[str, DimensionResult] = field(default_factory=dict)
    prev_run_latest_map: dict[str, DimensionResult] = field(default_factory=dict)


def _has_valid_score(dim: DimensionResult) -> bool:
    """Return True if the dimension carries a usable, trustworthy score.

    Requires a non-empty ``overall_score`` AND that the model actually
    inspected files. A coverage-0 eval (``files_read == 0``) is the stub
    ``_score_completed_evidence`` writes at cancel time when no findings
    landed; its score is meaningless and must not drive the accumulated
    Overview (the same ``filesRead > 0`` trust rule ``scoring_view`` uses).
    A missing ``files_read`` (None, legacy evals) is trusted as before.
    """
    if not dim.overall_score:
        return False
    return dim.files_read != 0


def _classify_dimension(
    dim: DimensionResult, run_id: str, run_info: RunInfo | None, is_first_run: bool,
    buckets: _DimensionBuckets,
) -> None:
    """Classify a single dimension into latest, previous-occurrence, or previous-run buckets."""
    dim_name = dim.dimension
    if not dim_name:
        return
    if dim_name not in buckets.latest_by_dimension:
        # Only accept as latest if the dimension has a valid score;
        # otherwise keep searching older runs for a scored result.
        if _has_valid_score(dim):
            buckets.latest_by_dimension[dim_name] = replace(
                dim,
                from_run_id=run_id,
                from_date_iso=run_info.date_iso if run_info else None,
                from_date_label=run_info.date_label if run_info else None,
            )
    elif dim_name not in buckets.prev_occurrence:
        buckets.prev_occurrence[dim_name] = replace(dim, run_id=run_id)
    if not is_first_run and dim_name not in buckets.prev_run_latest_map:
        buckets.prev_run_latest_map[dim_name] = dim


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
    get_run_data: Callable[[str], list[DimensionResult]] | None = None,
) -> tuple[dict[str, DimensionResult], dict[str, DimensionResult], list[DimensionResult]]:
    """Build accumulated data structures in a single sequential pass."""
    run_lookup = {r.run_id: r for r in all_run_infos}
    buckets = _DimensionBuckets()
    _fetch = get_run_data or (lambda rid: read_run_data(reports_root, project, rid))

    for run_idx_i, run_id in enumerate(runs):
        run_info = run_lookup.get(run_id)
        for dim in _fetch(run_id):
            _classify_dimension(dim, run_id, run_info, run_idx_i == 0, buckets)

    return (
        buckets.latest_by_dimension,
        buckets.prev_occurrence,
        list(buckets.prev_run_latest_map.values()),
    )
