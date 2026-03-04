from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from codecompass.action_provider import ActionProvider
from codecompass.action_provider_jobs import JobManager
from codecompass._fs_evaluation_mixin import FsEvaluationMixin
from codecompass._fs_tooling_mixin import FsToolingMixin
from codecompass.adapters.fs.report_parser import (
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


def _parse_violations_from_evidence(evidence_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        data = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    violations = []
    for raw_key, pdata in (data.get("principles") or {}).items():
        label = pdata.get("display_name") or raw_key
        for v in pdata.get("violations") or []:
            f = v.get("file")
            line = v.get("line")
            violations.append({
                "principle": label,
                "file": f"{f}:{line}" if f and line else f,
                "line": line,
                "reason": v.get("reason"),
                "snippet": v.get("snippet"),
                "severity": v.get("severity") or "minor",
            })
    return {"dimension": dimension, "runId": run_id, "project": project, "violations": violations, "partial": True}


def _texts_from_assistant(event: dict) -> list[str]:
    texts: list[str] = []
    for block in (event.get("message") or {}).get("content") or []:
        if block.get("type") == "text" and block.get("text"):
            texts.append(block["text"])
    return texts


def _texts_from_result(event: dict) -> list[str]:
    r = event.get("result")
    return [r] if r else []


def _texts_from_item_completed(event: dict) -> list[str]:
    texts: list[str] = []
    item = event.get("item") or {}
    if item.get("type") == "agent_message":
        if item.get("text"):
            texts.append(item["text"])
        for block in item.get("content") or []:
            if block.get("type") in ("text", "output_text") and block.get("text"):
                texts.append(block["text"])
    return texts


_TEXT_EXTRACTORS: dict[str, callable] = {
    "assistant": _texts_from_assistant,
    "result": _texts_from_result,
    "item.completed": _texts_from_item_completed,
}


def _parse_violations_from_stream(stream_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        content = stream_path.read_text()
    except OSError:
        return None
    violations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        extractor = _TEXT_EXTRACTORS.get(event.get("type"))
        texts = extractor(event) if extractor else []
        for text in texts:
            for tl in text.splitlines():
                t = tl.strip()
                if not t.startswith("{"):
                    continue
                try:
                    obj = json.loads(t)
                except json.JSONDecodeError:
                    continue
                if not obj.get("p") or obj.get("t") != "violation":
                    continue
                key = f"{obj['p']}:{obj.get('file', '')}:{obj.get('line', '')}"
                if key in seen:
                    continue
                seen.add(key)
                snippet = obj.get("snippet")
                violations.append({
                    "principle": obj.get("d") or obj["p"],
                    "file": obj.get("file"),
                    "line": obj.get("line"),
                    "reason": obj.get("reason"),
                    "snippet": str(snippet).splitlines()[0].strip() if snippet else None,
                    "severity": obj.get("severity") or "minor",
                })
    return {"dimension": dimension, "runId": run_id, "project": project, "violations": violations, "partial": True}


class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    def __init__(self, job_manager: JobManager | None = None) -> None:
        self._jobs = job_manager or JobManager()
        self._model_fetchers: dict[str, callable] = {
            "claude": self._get_claude_models,
        }
    def list_projects(self, reports_dir: str):
        reports_root = Path(reports_dir)
        projects = []
        for entry in safe_read_dir(reports_root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            runs = list_runs(reports_root, entry.name)
            if not runs:
                continue
            parent = None
            discipline = None
            path = None
            location = None
            display_name = None
            project_name = entry.name  # fallback: use dir name
            info_path = reports_root / entry.name / "repository_info.json"
            if info_path.exists():
                try:
                    info = json.loads(info_path.read_text())
                    parent = info.get("parent") or None
                    discipline = info.get("discipline") or None
                    path = info.get("path") or None
                    location = info.get("location") or None
                    display_name = info.get("displayName") or None
                    project_name = info.get("name") or entry.name
                except (json.JSONDecodeError, OSError):
                    pass
            latest_grade = None
            latest_score = None
            files_count = None
            try:
                dims = read_run_data(reports_root, entry.name, runs[0].run_id)
                summary = summarize_dimensions(dims)
                latest_grade = summary.get("overallGrade")
                latest_score = summary.get("numericAverage")
                files_count = next((d.get("sourceFileCount") for d in dims if d.get("sourceFileCount")), None)
            except Exception:
                pass
            path_exists = Path(path).exists() if location == "local" and path else None
            projects.append(
                {
                    "id": entry.name,
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
            )
        projects.sort(key=lambda item: item["name"])
        # Auto-detect parent for local projects that have no explicit parent
        local_with_path = [p for p in projects if p.get("location") == "local" and p.get("path")]
        for p in projects:
            if p.get("parent") is not None:
                continue
            if p.get("location") != "local" or not p.get("path"):
                continue
            p_path = p["path"].rstrip("/")
            best_parent = None
            best_len = 0
            for candidate in local_with_path:
                if candidate["id"] == p["id"]:
                    continue
                c_path = candidate["path"].rstrip("/")
                if p_path.startswith(c_path + "/") and len(c_path) > best_len:
                    best_parent = candidate["id"]
                    best_len = len(c_path)
            if best_parent:
                p["parent"] = best_parent
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

    def get_project_info(self, reports_dir: str, project: str):
        info_path = Path(reports_dir) / project / "repository_info.json"
        if not info_path.exists():
            return None
        try:
            info = json.loads(info_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        discipline = info.get("discipline")

        # Discipline may be null for projects evaluated via CLI — infer it from
        # the most recent evidence file, which always records the discipline.
        if not discipline:
            reports_root = Path(reports_dir)
            for run in sorted(safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
                if not run.is_dir():
                    continue
                for ev in safe_read_dir(reports_root / project / run.name / "evidence"):
                    if ev.name.endswith("_evidence.json"):
                        try:
                            d = json.loads(Path(ev.path).read_text()).get("discipline")
                            if d:
                                discipline = d
                        except Exception:
                            pass
                if discipline:
                    break

        available_dimensions: list[str] = []
        if discipline:
            try:
                from codecompass.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository
                from codecompass.config.paths import default_paths
                from codecompass.evaluate.lib.dimensions import list_available_dimensions
                paths = default_paths()
                evaluators = FilesystemEvaluatorsRepository(root=paths.vroot)
                available_dimensions = list_available_dimensions(evaluators, discipline)
            except Exception:
                pass

        return {**info, "discipline": discipline, "availableDimensions": available_dimensions}

    def get_dashboard(self, reports_dir: str, project: str, run: str):
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

        previous_by_dimension: dict[str, dict[str, Any]] = {}
        stale_dim_map: dict[str, dict[str, Any]] = {}
        skip_grades = {"NA", "N/A", "INSUFFICIENT"}

        run_data_cache: dict[str, list[dict[str, Any]]] = {}
        def get_run_dimensions(run_id: str) -> list[dict[str, Any]]:
            if run_id not in run_data_cache:
                run_data_cache[run_id] = read_run_data(reports_root, project, run_id)
            return run_data_cache[run_id]

        non_na_count: dict[str, int] = {}
        stale_previous_by_dimension: dict[str, dict[str, Any]] = {}

        for i in range(selected_index + 1, len(runs)):
            run_dimensions = get_run_dimensions(runs[i].run_id)
            for dim in run_dimensions:
                dim_name = dim.get("dimension")
                if not dim_name:
                    continue
                grade = dim.get("overallGrade")
                grade_is_na = not grade or str(grade).upper() in skip_grades

                if dim_name in selected_dim_names:
                    if dim_name not in previous_by_dimension and not grade_is_na:
                        previous_by_dimension[dim_name] = {**dim, "runId": runs[i].run_id}
                else:
                    if dim_name not in stale_dim_map:
                        stale_dim_map[dim_name] = {
                            **dim,
                            "stale": True,
                            "fromRunId": runs[i].run_id,
                            "fromDateISO": runs[i].date_iso,
                            "fromDateLabel": runs[i].date_label,
                        }
                    if not grade_is_na:
                        non_na_count[dim_name] = non_na_count.get(dim_name, 0) + 1
                        if non_na_count[dim_name] == 2 and dim_name not in stale_previous_by_dimension:
                            stale_previous_by_dimension[dim_name] = dim

        for i in range(0, selected_index):
            run_dimensions = get_run_dimensions(runs[i].run_id)
            for dim in run_dimensions:
                dim_name = dim.get("dimension")
                if dim_name and dim_name not in selected_dim_names and dim_name not in stale_dim_map:
                    stale_dim_map[dim_name] = {
                        **dim,
                        "stale": True,
                        "fromRunId": runs[i].run_id,
                        "fromDateISO": runs[i].date_iso,
                        "fromDateLabel": runs[i].date_label,
                    }

        stale_dimensions = sorted(stale_dim_map.values(), key=lambda d: d.get("dimension") or "")

        dimensions_with_trend = []
        for dim in selected_dimensions:
            previous = previous_by_dimension.get(dim.get("dimension"))
            trend = calculate_trend(dim.get("overallScore"), previous.get("overallScore") if previous else None)
            dimensions_with_trend.append(
                {
                    **dim,
                    "trend": trend,
                    "previousRunId": previous.get("runId") if previous else None,
                    "previousScore": previous.get("overallScore") if previous else None,
                }
            )

        # Build trend using accumulated scores (same logic as get_accumulated):
        # for each run, compute the score using the best/latest dimension data
        # available up to and including that run, not just that run's data alone.
        trend = []
        acc_by_dim: dict[str, dict[str, Any]] = {}
        for item in reversed(runs):  # oldest → newest
            run_dims = get_run_dimensions(item.run_id)
            for dim in run_dims:
                dim_name = dim.get("dimension")
                if dim_name:
                    acc_by_dim[dim_name] = dim  # latest run wins
            # Skip runs with no scored dimensions (e.g. in-progress evaluations)
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
        trend.reverse()  # back to newest-first

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

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None):
        reports_root = Path(reports_dir)
        project_path = reports_root / project
        if not project_path.exists():
            return None

        all_run_infos = list_runs(reports_root, project)  # newest first
        if as_of:
            # Find the as_of run index and keep only that run and older
            as_of_idx = next((i for i, r in enumerate(all_run_infos) if r.run_id == as_of), None)
            if as_of_idx is not None:
                all_run_infos = all_run_infos[as_of_idx:]
            else:
                all_run_infos = []
        runs = [r.run_id for r in all_run_infos]
        if not runs:
            return None

        # Pre-read all run data once to avoid redundant disk reads across the loops below.
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

        all_dimensions = list(latest_by_dimension.values())

        # Build ordered list of run IDs for index-based comparison
        run_order = runs  # already newest-first
        dimensions_with_trend = []
        for dim in all_dimensions:
            from_run = dim.get("fromRunId")
            dim_name = dim.get("dimension")
            previous = None
            if from_run:
                from_idx = run_order.index(from_run) if from_run in run_order else -1
                if from_idx >= 0:
                    for rid in run_order[from_idx + 1:]:
                        d = next((x for x in all_run_data.get(rid, []) if x.get("dimension") == dim_name), None)
                        if d:
                            previous = {"runId": rid, "dimension": d}
                            break
            trend = calculate_trend(dim.get("overallScore"), previous.get("dimension", {}).get("overallScore") if previous else None)
            dimensions_with_trend.append(
                {
                    **dim,
                    "trend": trend,
                    "previousRunId": previous.get("runId") if previous else None,
                    "previousScore": previous.get("dimension", {}).get("overallScore") if previous else None,
                }
            )

        grades = [d.get("overallGrade") for d in all_dimensions if d.get("overallGrade")]
        scores = [d.get("overallScore") for d in all_dimensions if d.get("overallScore")]

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

        numeric_scores = [score for score in (parse_numeric_score(s) for s in scores) if score is not None]
        avg_score = round(sum(numeric_scores) / len(numeric_scores), 1) if numeric_scores else None

        # Compute previous overall average by re-accumulating over runs[1:] (i.e., excluding
        # the latest run). This gives the true prior snapshot rather than mixing each dimension's
        # individual previousScore which may point to different runs.
        prev_avg_score = None
        if len(runs) >= 2:
            prev_latest_by_dimension: dict[str, dict[str, Any]] = {}
            for run_id in runs[1:]:
                for dim in all_run_data[run_id]:
                    dim_name = dim.get("dimension")
                    if dim_name and dim_name not in prev_latest_by_dimension:
                        prev_latest_by_dimension[dim_name] = dim
            prev_scores_raw = [d.get("overallScore") for d in prev_latest_by_dimension.values() if d.get("overallScore")]
            prev_numeric_scores = [s for s in (parse_numeric_score(s) for s in prev_scores_raw) if s is not None]
            prev_avg_score = round(sum(prev_numeric_scores) / len(prev_numeric_scores), 1) if prev_numeric_scores else None

        return {
            "project": project,
            "dimensions": dimensions_with_trend,
            "summary": {
                "overallGrade": most_frequent_grade(grades),
                "numericAverage": avg_score,
                "previousNumericAverage": prev_avg_score,
                "totalViolations": total_violations,
                "totalCompliance": total_compliance,
                "dimensionCount": len(dimensions_with_trend),
                "severity": {"critical": critical, "major": major, "minor": minor},
            },
        }

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str):
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
            return _parse_violations_from_evidence(evidence_path, project, run_id, dimension)
        stream_path = base / "evidence" / f"{dimension}_live.stream"
        if stream_path.exists():
            return _parse_violations_from_stream(stream_path, project, run_id, dimension)
        return None

    def get_violations(self, reports_dir: str, project: str, run_id: str):
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

        files = sorted(summary["byFile"].values(), key=lambda item: item["count"], reverse=True)[:20]
        summary["files"] = files
        summary.pop("byFile", None)
        return summary

    # browse_repo, get_ai_clients, get_client_models → FsToolingMixin
    # start_evaluation, get_evaluation_status, cancel_evaluation → FsEvaluationMixin
