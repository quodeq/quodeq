from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from quodeq.action_provider import ActionProvider
from quodeq.action_provider_jobs import JobManager
from quodeq._fs_evaluation_mixin import FsEvaluationMixin
from quodeq._fs_tooling_mixin import FsToolingMixin
from quodeq._fs_violations import parse_violations_from_evidence, parse_violations_from_jsonl, parse_violations_from_stream
from quodeq.adapters.fs.report_parser import (
    calculate_trend,
    list_runs,
    most_frequent_grade,
    parse_eval_from_json,
    parse_eval_markdown,
    parse_evidence_file,
    parse_numeric_score,
    read_run_data,
    safe_read_dir,
    summarize_dimensions,
)


_SKIP_GRADES = {"NA", "N/A", "INSUFFICIENT"}
_MAX_VIOLATION_FILES = 20


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


def _collect_stale_dimensions(
    runs, selected_index: int, selected_dim_names: set, get_run_dimensions
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Find dimensions present in other runs but absent from the selected run."""
    stale_dim_map: dict[str, dict[str, Any]] = {}
    non_na_count: dict[str, int] = {}
    stale_previous_by_dimension: dict[str, dict[str, Any]] = {}

    for older_idx in range(selected_index + 1, len(runs)):
        run_dimensions = get_run_dimensions(runs[older_idx].run_id)
        for dim in run_dimensions:
            dim_name = dim.get("dimension")
            if not dim_name or dim_name in selected_dim_names:
                continue
            if dim_name not in stale_dim_map:
                stale_dim_map[dim_name] = {
                    **dim,
                    "stale": True,
                    "fromRunId": runs[older_idx].run_id,
                    "fromDateISO": runs[older_idx].date_iso,
                    "fromDateLabel": runs[older_idx].date_label,
                }
            grade = dim.get("overallGrade")
            if grade and str(grade).upper() not in _SKIP_GRADES:
                non_na_count[dim_name] = non_na_count.get(dim_name, 0) + 1
                if non_na_count[dim_name] == 2 and dim_name not in stale_previous_by_dimension:
                    stale_previous_by_dimension[dim_name] = dim

    for newer_idx in range(0, selected_index):
        run_dimensions = get_run_dimensions(runs[newer_idx].run_id)
        for dim in run_dimensions:
            dim_name = dim.get("dimension")
            if dim_name and dim_name not in selected_dim_names and dim_name not in stale_dim_map:
                stale_dim_map[dim_name] = {
                    **dim,
                    "stale": True,
                    "fromRunId": runs[newer_idx].run_id,
                    "fromDateISO": runs[newer_idx].date_iso,
                    "fromDateLabel": runs[newer_idx].date_label,
                }

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
    for item in reversed(runs):  # oldest → newest
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


def _read_all_run_data(
    reports_root: Path, project: str, all_run_infos, runs: list[str]
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


def _compute_accumulated_trends(
    all_dimensions: list[dict[str, Any]], runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Compute trend data for each accumulated dimension."""
    result = []
    for dim in all_dimensions:
        from_run = dim.get("fromRunId")
        dim_name = dim.get("dimension")
        previous = None
        if from_run:
            from_idx = runs.index(from_run) if from_run in runs else -1
            if from_idx >= 0:
                for rid in runs[from_idx + 1:]:
                    found = next((x for x in all_run_data.get(rid, []) if x.get("dimension") == dim_name), None)
                    if found:
                        previous = {"runId": rid, "dimension": found}
                        break
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


def _compute_accumulated_scores(
    all_dimensions: list[dict[str, Any]], runs: list[str], all_run_data: dict[str, list[dict[str, Any]]]
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    scores = [d.get("overallScore") for d in all_dimensions if d.get("overallScore")]
    numeric_scores = [s for s in (parse_numeric_score(v) for v in scores) if s is not None]
    avg_score = round(sum(numeric_scores) / len(numeric_scores), 1) if numeric_scores else None

    prev_avg_score = None
    if len(runs) >= 2:
        prev_latest: dict[str, dict[str, Any]] = {}
        for run_id in runs[1:]:
            for dim in all_run_data[run_id]:
                dim_name = dim.get("dimension")
                if dim_name and dim_name not in prev_latest:
                    prev_latest[dim_name] = dim
        prev_raw = [d.get("overallScore") for d in prev_latest.values() if d.get("overallScore")]
        prev_numeric = [s for s in (parse_numeric_score(v) for v in prev_raw) if s is not None]
        prev_avg_score = round(sum(prev_numeric) / len(prev_numeric), 1) if prev_numeric else None
    return avg_score, prev_avg_score


def _build_project_entry(reports_root: Path, entry_name: str, runs) -> dict[str, Any]:
    """Build a single project dict from its directory and run list."""
    parent = None
    discipline = None
    path = None
    location = None
    display_name = None
    project_name = entry_name
    info_path = reports_root / entry_name / "repository_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
            parent = info.get("parent") or None
            discipline = info.get("discipline") or None
            path = info.get("path") or None
            location = info.get("location") or None
            display_name = info.get("displayName") or None
            project_name = info.get("name") or entry_name
        except (json.JSONDecodeError, OSError):
            pass
    latest_grade = None
    latest_score = None
    files_count = None
    try:
        dims = read_run_data(reports_root, entry_name, runs[0].run_id)
        summary = summarize_dimensions(dims)
        latest_grade = summary.get("overallGrade")
        latest_score = summary.get("numericAverage")
        files_count = next((d.get("sourceFileCount") for d in dims if d.get("sourceFileCount")), None)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass
    path_exists = Path(path).exists() if location == "local" and path else None
    return {
        "id": entry_name,
        "name": project_name,
        "runsCount": len(runs),
        "latestRunId": runs[0].run_id,
        "latestDate": runs[0].date_iso,
        "parent": parent,
        "displayName": display_name,
        "discipline": discipline,
        "path": path,
        "location": location,
        "pathExists": path_exists,
        "filesCount": files_count,
        "latestGrade": latest_grade,
        "latestScore": latest_score,
    }


def _auto_detect_parents(projects: list[dict[str, Any]]) -> None:
    """Set parent for local projects that share a path prefix with another project."""
    local_with_path = [p for p in projects if p.get("location") == "local" and p.get("path")]
    for project in projects:
        if project.get("parent") is not None:
            continue
        if project.get("location") != "local" or not project.get("path"):
            continue
        p_path = project["path"].rstrip("/")
        best_parent = None
        best_len = 0
        for candidate in local_with_path:
            if candidate["id"] == project["id"]:
                continue
            c_path = candidate["path"].rstrip("/")
            if p_path.startswith(c_path + "/") and len(c_path) > best_len:
                best_parent = candidate["id"]
                best_len = len(c_path)
        if best_parent:
            project["parent"] = best_parent


def _infer_discipline(reports_root: Path, project: str) -> str | None:
    """Infer discipline from the most recent evidence file."""
    for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
        if not run.is_dir():
            continue
        for ev in safe_read_dir(reports_root / project / run.name / "evidence"):
            if ev.name.endswith("_evidence.json"):
                try:
                    found = json.loads(Path(ev.path).read_text()).get("discipline")
                    if found:
                        return found
                except (OSError, json.JSONDecodeError):
                    pass
    return None


def _list_available_dimensions_for_discipline(discipline: str) -> list[str]:
    """Resolve available dimensions for a plugin via its dimensions.json."""
    try:
        from quodeq.config.paths import default_paths
        plugin_dir = default_paths().evaluators_dir / discipline
        dims_file = plugin_dir / "dimensions.json"
        if dims_file.exists():
            data = json.loads(dims_file.read_text())
            return [d["id"] for d in data.get("applies", [])]
        return []
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return []


class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    def __init__(self, job_manager: JobManager | None = None) -> None:
        self._jobs = job_manager or JobManager()
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        reports_root = Path(reports_dir)
        projects = []
        for entry in safe_read_dir(reports_root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            runs = list_runs(reports_root, entry.name)
            if not runs:
                continue
            projects.append(_build_project_entry(reports_root, entry.name, runs))
        projects.sort(key=lambda item: item["name"])
        _auto_detect_parents(projects)
        return {"projects": projects}

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        info_path = Path(reports_dir) / project / "repository_info.json"
        if not info_path.exists():
            return False
        try:
            info = json.loads(info_path.read_text())
            info["path"] = new_path
            info["location"] = "local"
            info_path.write_text(json.dumps(info, indent=2))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def delete_project(self, reports_dir: str, project: str) -> bool:
        import shutil
        project_path = Path(reports_dir) / project
        if not project_path.exists() or not project_path.is_dir():
            return False
        shutil.rmtree(project_path)
        return True

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        info_path = Path(reports_dir) / project / "repository_info.json"
        if not info_path.exists():
            return None
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        discipline = info.get("discipline") or _infer_discipline(Path(reports_dir), project)
        available_dimensions = _list_available_dimensions_for_discipline(discipline) if discipline else []
        return {**info, "discipline": discipline, "availableDimensions": available_dimensions}

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
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

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
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

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
        base = Path(reports_dir) / project / run_id
        eval_path = base / "evaluation" / f"{dimension}.json"
        if eval_path.exists():
            return parse_eval_from_json(eval_path, project, run_id, dimension)
        markdown_path = base / "evaluation" / f"{dimension}_eval.md"
        if markdown_path.exists():
            try:
                content = markdown_path.read_text()
            except OSError:
                return None
            return parse_eval_markdown(content, project, run_id, dimension)
        evidence_path = base / "evidence" / f"{dimension}_evidence.json"
        if evidence_path.exists():
            return parse_violations_from_evidence(evidence_path, project, run_id, dimension)
        jsonl_path = base / "evidence" / f"{dimension}_evidence.jsonl"
        stream_path = base / "evidence" / f"{dimension}_live.stream"
        if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
            return parse_violations_from_jsonl(jsonl_path, stream_path, project, run_id, dimension)
        if stream_path.exists():
            return parse_violations_from_stream(stream_path, project, run_id, dimension)
        # Run exists but dimension hasn't started yet
        if base.is_dir():
            return {"waiting": True, "project": project, "runId": run_id, "dimension": dimension}
        return None

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> dict[str, Any]:
        dashboard = self.get_dashboard(reports_dir, project, run_id)
        summary = {
            "total": 0,
            "critical": 0,
            "major": 0,
            "minor": 0,
            "byFile": {},
        }
        for dim in dashboard.get("dimensions", []) or []:
            summary["total"] += dim.get("totals", {}).get("violationCount", 0)
            severity = dim.get("totals", {}).get("severity", {})
            summary["critical"] += severity.get("critical", 0)
            summary["major"] += severity.get("major", 0)
            summary["minor"] += severity.get("minor", 0)

            for violation in dim.get("violations", []) or []:
                file_path = violation.get("file")
                if not file_path:
                    continue
                entry = summary["byFile"].setdefault(
                    file_path, {"path": file_path, "count": 0, "critical": 0, "major": 0, "minor": 0}
                )
                entry["count"] += 1
                sev = violation.get("severity", "minor")
                if sev in entry:
                    entry[sev] += 1

        files = sorted(summary["byFile"].values(), key=lambda item: item["count"], reverse=True)[:_MAX_VIOLATION_FILES]
        summary["files"] = files
        summary.pop("byFile", None)
        return summary

    # browse_repo, get_ai_clients, get_client_models → FsToolingMixin
    # start_evaluation, get_evaluation_status, cancel_evaluation → FsEvaluationMixin
