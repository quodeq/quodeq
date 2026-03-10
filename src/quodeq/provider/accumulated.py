"""Accumulated (cross-run) view logic for the filesystem action provider."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.adapters.fs.report_parser import (
    RunInfo,
    calculate_trend,
    list_runs,
    most_frequent_grade,
    parse_numeric_score,
    read_run_data,
)


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos: list[RunInfo], runs: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Pre-read all run data and build the latest-by-dimension lookup."""
    run_lookup = {r.run_id: r for r in all_run_infos}
    all_run_data: dict[str, list[dict[str, Any]]] = {}
    latest_by_dimension: dict[str, dict[str, Any]] = {}
    for run_id in runs:
        dims = read_run_data(reports_root, project, run_id)
        all_run_data[run_id] = dims
        run_info = run_lookup.get(run_id)
        for dim in dims:
            dim_name = dim.get("dimension")
            if dim_name and dim_name not in latest_by_dimension:
                latest_by_dimension[dim_name] = {
                    **dim,
                    "fromRunId": run_id,
                    "fromDateISO": run_info.date_iso if run_info else None,
                    "fromDateLabel": run_info.date_label if run_info else None,
                }
    return all_run_data, latest_by_dimension


def _find_previous_run(
    dim_name: str, from_run: str, runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """Find the previous run containing *dim_name* after *from_run*."""
    from_idx = runs.index(from_run) if from_run in runs else -1
    if from_idx < 0:
        return None
    for rid in runs[from_idx + 1:]:
        found = next((x for x in all_run_data.get(rid, []) if x.get("dimension") == dim_name), None)
        if found:
            return {"runId": rid, "dimension": found}
    return None


def _compute_accumulated_trends(
    all_dimensions: list[dict[str, Any]], runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Compute trend data for each accumulated dimension."""
    result = []
    for dim in all_dimensions:
        from_run = dim.get("fromRunId")
        previous = _find_previous_run(dim.get("dimension"), from_run, runs, all_run_data) if from_run else None
        trend = calculate_trend(dim.get("overallScore"), previous.get("dimension", {}).get("overallScore") if previous else None)
        result.append(
            {
                **dim,
                "trend": trend,
                "previousRunId": previous.get("runId") if previous else None,
                "previousScore": previous.get("dimension", {}).get("overallScore") if previous else None,
            }
        )
    return result


def _aggregate_severity_counts(all_dimensions: list[dict[str, Any]]) -> dict[str, int]:
    """Sum violation/compliance counts and severity buckets across dimensions."""
    total_violations = 0
    total_compliance = 0
    critical = 0
    major = 0
    minor = 0
    for dim in all_dimensions:
        totals = dim.get("totals", {})
        severity = totals.get("severity", {}) if totals else {}
        total_violations += totals.get("violationCount", 0) if totals else 0
        total_compliance += totals.get("complianceCount", 0) if totals else 0
        critical += severity.get("critical", 0)
        major += severity.get("major", 0)
        minor += severity.get("minor", 0)
    return {
        "totalViolations": total_violations,
        "totalCompliance": total_compliance,
        "critical": critical,
        "major": major,
        "minor": minor,
    }


def numeric_average(dimensions: list[dict[str, Any]]) -> float | None:
    """Compute the average numeric score from a list of dimension dicts."""
    raw = [d.get("overallScore") for d in dimensions if d.get("overallScore")]
    numeric = [s for s in (parse_numeric_score(v) for v in raw) if s is not None]
    return round(sum(numeric) / len(numeric), 1) if numeric else None


def _collect_previous_latest(
    runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Collect the most recent dimension data from all runs except the first."""
    prev_latest: dict[str, dict[str, Any]] = {}
    for run_id in runs[1:]:
        for dim in all_run_data[run_id]:
            dim_name = dim.get("dimension")
            if dim_name and dim_name not in prev_latest:
                prev_latest[dim_name] = dim
    return list(prev_latest.values())


def _compute_accumulated_scores(
    all_dimensions: list[dict[str, Any]], runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    avg_score = numeric_average(all_dimensions)
    prev_avg_score = None
    if len(runs) >= 2:
        prev_avg_score = numeric_average(_collect_previous_latest(runs, all_run_data))
    return avg_score, prev_avg_score


def compute_accumulated(reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*."""
    reports_root = Path(reports_dir)
    project_path = reports_root / project
    if not project_path.exists():
        return None

    all_run_infos = list_runs(reports_root, project)  # newest first
    if as_of:
        as_of_idx = next((idx for idx, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[as_of_idx:] if as_of_idx is not None else []
    runs = [r.run_id for r in all_run_infos]
    if not runs:
        return None

    all_run_data, latest_by_dimension = _read_all_run_data(reports_root, project, all_run_infos, runs)
    all_dimensions = list(latest_by_dimension.values())
    dimensions_with_trend = _compute_accumulated_trends(all_dimensions, runs, all_run_data)
    severity = _aggregate_severity_counts(all_dimensions)
    avg_score, prev_avg_score = _compute_accumulated_scores(all_dimensions, runs, all_run_data)

    return {
        "project": project,
        "dimensions": dimensions_with_trend,
        "summary": {
            "overallGrade": most_frequent_grade(
                [d.get("overallGrade") for d in all_dimensions if d.get("overallGrade")]
            ),
            "numericAverage": avg_score,
            "previousNumericAverage": prev_avg_score,
            "totalViolations": severity["totalViolations"],
            "totalCompliance": severity["totalCompliance"],
            "dimensionCount": len(dimensions_with_trend),
            "severity": {"critical": severity["critical"], "major": severity["major"], "minor": severity["minor"]},
        },
    }
