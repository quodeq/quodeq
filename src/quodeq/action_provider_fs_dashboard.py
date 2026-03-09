"""Dashboard and accumulated-view logic, split from action_provider_fs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.action_provider_fs_accumulated import compute_accumulated  # noqa: F401
from quodeq.adapters.fs.report_parser import (
    calculate_trend,
    list_runs,
    most_frequent_grade,
    parse_numeric_score,
    read_run_data,
    summarize_dimensions,
)
# parse_numeric_score is used by _build_accumulated_trend


_SKIP_GRADES = {"NA", "N/A", "INSUFFICIENT"}


def _collect_previous_scores(
    runs, selected_index: int, selected_dim_names: set, get_run_dimensions
) -> dict[str, dict[str, Any]]:
    """Find the most recent previous score for each dimension in the selected run."""
    previous_by_dimension: dict[str, dict[str, Any]] = {}
    for older_idx in range(selected_index + 1, len(runs)):
        run_dimensions = get_run_dimensions(runs[older_idx].run_id)
        for dim in run_dimensions:
            dim_name = dim.get("dimension")
            if not dim_name or dim_name not in selected_dim_names:
                continue
            grade = dim.get("overallGrade")
            if not grade or str(grade).upper() in _SKIP_GRADES:
                continue
            if dim_name not in previous_by_dimension:
                previous_by_dimension[dim_name] = {**dim, "runId": runs[older_idx].run_id}
    return previous_by_dimension


def _find_stale_from_run(
    run_dir, selected_dim_names: set, get_run_dimensions
) -> list[dict]:
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


def _record_stale_entry(entry: dict, stale_dim_map: dict[str, dict[str, Any]]) -> None:
    """Add a stale dimension entry to the map if not already present."""
    dim_name = entry["dim_name"]
    if dim_name not in stale_dim_map:
        stale_dim_map[dim_name] = {
            **entry["dim"],
            "stale": True,
            "fromRunId": entry["run_id"],
            "fromDateISO": entry["date_iso"],
            "fromDateLabel": entry["date_label"],
        }


def _collect_stale_dimensions(
    runs, selected_index: int, selected_dim_names: set, get_run_dimensions
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Find dimensions present in other runs but absent from the selected run."""
    stale_dim_map: dict[str, dict[str, Any]] = {}
    non_na_count: dict[str, int] = {}
    stale_previous_by_dimension: dict[str, dict[str, Any]] = {}

    for older_idx in range(selected_index + 1, len(runs)):
        for entry in _find_stale_from_run(runs[older_idx], selected_dim_names, get_run_dimensions):
            _record_stale_entry(entry, stale_dim_map)
            grade = entry["grade"]
            if grade and str(grade).upper() not in _SKIP_GRADES:
                dim_name = entry["dim_name"]
                non_na_count[dim_name] = non_na_count.get(dim_name, 0) + 1
                if non_na_count[dim_name] == 2 and dim_name not in stale_previous_by_dimension:
                    stale_previous_by_dimension[dim_name] = entry["dim"]

    for newer_idx in range(selected_index):
        for entry in _find_stale_from_run(runs[newer_idx], selected_dim_names, get_run_dimensions):
            _record_stale_entry(entry, stale_dim_map)

    stale_dimensions = sorted(stale_dim_map.values(), key=lambda d: d.get("dimension") or "")
    return stale_dimensions, stale_previous_by_dimension


def _enrich_dimensions_with_trend(
    selected_dimensions: list[dict[str, Any]], previous_by_dimension: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach trend and previous-run data to each selected dimension."""
    result = []
    for dim in selected_dimensions:
        previous = previous_by_dimension.get(dim.get("dimension"))
        trend = calculate_trend(dim.get("overallScore"), previous.get("overallScore") if previous else None)
        result.append(
            {
                **dim,
                "trend": trend,
                "previousRunId": previous.get("runId") if previous else None,
                "previousScore": previous.get("overallScore") if previous else None,
            }
        )
    return result


def _build_accumulated_trend(runs, get_run_dimensions) -> list[dict[str, Any]]:
    """Build trend using accumulated scores across all runs (oldest to newest)."""
    trend: list[dict[str, Any]] = []
    acc_by_dim: dict[str, dict[str, Any]] = {}
    for item in reversed(runs):  # oldest -> newest
        run_dims = get_run_dimensions(item.run_id)
        for dim in run_dims:
            dim_name = dim.get("dimension")
            if dim_name:
                acc_by_dim[dim_name] = dim
        if not run_dims:
            continue
        acc_scores = [
            s for s in (parse_numeric_score(d.get("overallScore")) for d in acc_by_dim.values())
            if s is not None
        ]
        acc_grades = [d.get("overallGrade") for d in acc_by_dim.values() if d.get("overallGrade")]
        trend.append(
            {
                "runId": item.run_id,
                "dateISO": item.date_iso,
                "dateLabel": item.date_label,
                "dimensionsCount": len(acc_by_dim),
                "overallGrade": most_frequent_grade(acc_grades) if acc_grades else None,
                "numericAverage": round(sum(acc_scores) / len(acc_scores), 1) if acc_scores else None,
            }
        )
    trend.reverse()
    return trend


def build_dashboard(reports_dir: str, project: str, run: str) -> dict[str, Any]:
    """Build a full dashboard response for *project* at *run*."""
    reports_root = Path(reports_dir)
    runs = list_runs(reports_root, project)
    if not runs:
        raise FileNotFoundError(f"No runs found for project: {project}")

    selected_run = runs[0] if run == "latest" else next((item for item in runs if item.run_id == run), None)
    if not selected_run:
        raise FileNotFoundError(f"Run not found: {run}")

    selected_dimensions = read_run_data(reports_root, project, selected_run.run_id)
    selected_summary = summarize_dimensions(selected_dimensions)
    selected_dim_names = {d.get("dimension") for d in selected_dimensions}
    selected_index = next((idx for idx, item in enumerate(runs) if item.run_id == selected_run.run_id), 0)

    run_data_cache: dict[str, list[dict[str, Any]]] = {}
    def get_run_dimensions(run_id: str) -> list[dict[str, Any]]:
        """Return dimension data for a run, using a cache to avoid re-reads."""
        if run_id not in run_data_cache:
            run_data_cache[run_id] = read_run_data(reports_root, project, run_id)
        return run_data_cache[run_id]

    previous_by_dimension = _collect_previous_scores(runs, selected_index, selected_dim_names, get_run_dimensions)
    stale_dimensions, stale_previous_by_dimension = (
        _collect_stale_dimensions(runs, selected_index, selected_dim_names, get_run_dimensions)
    )
    dimensions_with_trend = _enrich_dimensions_with_trend(selected_dimensions, previous_by_dimension)
    trend = _build_accumulated_trend(runs, get_run_dimensions)

    return {
        "project": project,
        "availableRuns": [
            {"runId": item.run_id, "dateISO": item.date_iso, "dateLabel": item.date_label}
            for item in runs
        ],
        "selectedRun": {"runId": selected_run.run_id, "dateISO": selected_run.date_iso, "dateLabel": selected_run.date_label},
        "summary": {**selected_summary, "dateISO": selected_run.date_iso, "dateLabel": selected_run.date_label},
        "trend": trend,
        "dimensions": dimensions_with_trend,
        "previousByDimension": previous_by_dimension,
        "stalePreviousByDimension": stale_previous_by_dimension,
        "staleDimensions": stale_dimensions,
    }


