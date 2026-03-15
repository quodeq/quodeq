"""Stale-dimension helpers for the dashboard provider."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from quodeq.shared.types import DimensionData

from quodeq.adapters.fs.report_parser import RunInfo

_SKIP_GRADES = {"NA", "N/A", "INSUFFICIENT"}


@dataclass
class StaleDimState:
    """Groups the three mutable tracking dicts used by collect_stale_dimensions."""
    stale_dim_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    non_na_count: dict[str, int] = field(default_factory=dict)
    stale_previous_by_dimension: dict[str, dict[str, Any]] = field(default_factory=dict)


def find_stale_from_run(
    run_dir: RunInfo, selected_dim_names: set[str],
    get_run_dimensions: Callable[[str], list[DimensionData]],
) -> list[DimensionData]:
    """Return stale dimension dicts found in a single run directory."""
    results: list[dict] = []
    run_dimensions = get_run_dimensions(run_dir.run_id)
    for dim in run_dimensions:
        dim_name = dim.get("dimension")
        if not dim_name or dim_name in selected_dim_names:
            continue
        results.append({
            "dim_name": dim_name,
            "dim": dim,
            "run_id": run_dir.run_id,
            "date_iso": run_dir.date_iso,
            "date_label": run_dir.date_label,
            "grade": dim.get("overallGrade"),
        })
    return results


def record_stale_entry(entry: dict, state: StaleDimState) -> None:
    """Add a stale dimension entry to the map if not already present."""
    dim_name = entry["dim_name"]
    if dim_name not in state.stale_dim_map:
        state.stale_dim_map[dim_name] = {
            **entry["dim"],
            "stale": True,
            "fromRunId": entry["run_id"],
            "fromDateISO": entry["date_iso"],
            "fromDateLabel": entry["date_label"],
        }


def track_stale_grade(entry: dict, state: StaleDimState) -> None:
    """Track grade counts for stale entries to identify the second valid score."""
    grade = entry["grade"]
    if not grade or str(grade).upper() in _SKIP_GRADES:
        return
    dim_name = entry["dim_name"]
    state.non_na_count[dim_name] = state.non_na_count.get(dim_name, 0) + 1
    if state.non_na_count[dim_name] == 2 and dim_name not in state.stale_previous_by_dimension:
        state.stale_previous_by_dimension[dim_name] = entry["dim"]


def collect_stale_dimensions(
    runs: list[RunInfo], selected_index: int, selected_dim_names: set[str],
    get_run_dimensions: Callable[[str], list[DimensionData]],
) -> tuple[list[DimensionData], dict[str, dict[str, Any]]]:
    """Find dimensions present in other runs but absent from the selected run."""
    state = StaleDimState()

    for older_idx in range(selected_index + 1, len(runs)):
        for entry in find_stale_from_run(runs[older_idx], selected_dim_names, get_run_dimensions):
            record_stale_entry(entry, state)
            track_stale_grade(entry, state)

    for newer_idx in range(selected_index):
        for entry in find_stale_from_run(runs[newer_idx], selected_dim_names, get_run_dimensions):
            record_stale_entry(entry, state)

    stale_dimensions = sorted(state.stale_dim_map.values(), key=lambda d: d.get("dimension") or "")
    return stale_dimensions, state.stale_previous_by_dimension
