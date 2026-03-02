from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import Any

from codecompass.action_provider import ActionProvider
from codecompass.action_provider_jobs import JobManager
from codecompass.adapters.fs.report_parser import (
    RunInfo,
    _build_repository_info,
    _build_totals,
    _calculate_trend,
    _clean_cell,
    _extract_exec_summary,
    _is_divider_row,
    _list_runs,
    _most_frequent_grade,
    _parse_eval_from_json,
    _parse_eval_markdown,
    _parse_evidence_file,
    _parse_numeric_score,
    _parse_report_json,
    _parse_run_id_date,
    _read_run_data,
    _safe_read_dir,
    _split_table_row,
    _summarize_dimensions,
)
from codecompass.evaluate.lib.repo_handler import is_repo_url


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
        texts: list[str] = []
        etype = event.get("type")
        if etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
        elif etype == "result":
            if event.get("result"):
                texts.append(event["result"])
        elif etype == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                if item.get("text"):
                    texts.append(item["text"])
                for block in item.get("content") or []:
                    if block.get("type") in ("text", "output_text") and block.get("text"):
                        texts.append(block["text"])
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


class FilesystemActionProvider(ActionProvider):
    def __init__(self, job_manager: JobManager | None = None) -> None:
        self._jobs = job_manager or JobManager()
    def list_projects(self, reports_dir: str):
        reports_root = Path(reports_dir)
        projects = []
        for entry in _safe_read_dir(reports_root):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            runs = _list_runs(reports_root, entry.name)
            if not runs:
                continue
            projects.append(
                {
                    "name": entry.name,
                    "runsCount": len(runs),
                    "latestRunId": runs[0].run_id if runs else None,
                    "latestDate": runs[0].date_iso if runs else None,
                }
            )
        projects.sort(key=lambda item: item["name"])
        return {"projects": projects}

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
            for run in sorted(_safe_read_dir(reports_root / project), key=lambda e: e.name, reverse=True):
                if not run.is_dir():
                    continue
                for ev in _safe_read_dir(reports_root / project / run.name / "evidence"):
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
        runs = _list_runs(reports_root, project)
        if not runs:
            raise FileNotFoundError(f"No runs found for project: {project}")

        selected_run = runs[0] if run == "latest" else next((item for item in runs if item.run_id == run), None)
        if not selected_run:
            raise FileNotFoundError(f"Run not found: {run}")

        selected_dimensions = _read_run_data(reports_root, project, selected_run.run_id)
        selected_summary = _summarize_dimensions(selected_dimensions)
        selected_dim_names = {d.get("dimension") for d in selected_dimensions}

        selected_index = next((idx for idx, item in enumerate(runs) if item.run_id == selected_run.run_id), 0)

        previous_by_dimension: dict[str, dict[str, Any]] = {}
        stale_dim_map: dict[str, dict[str, Any]] = {}
        skip_grades = {"NA", "N/A", "INSUFFICIENT"}

        run_data_cache: dict[str, list[dict[str, Any]]] = {}
        def get_run_dimensions(run_id: str) -> list[dict[str, Any]]:
            if run_id not in run_data_cache:
                run_data_cache[run_id] = _read_run_data(reports_root, project, run_id)
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
                    }

        stale_dimensions = sorted(stale_dim_map.values(), key=lambda d: d.get("dimension") or "")

        dimensions_with_trend = []
        for dim in selected_dimensions:
            previous = previous_by_dimension.get(dim.get("dimension"))
            trend = _calculate_trend(dim.get("overallScore"), previous.get("overallScore") if previous else None)
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
            for dim in get_run_dimensions(item.run_id):
                dim_name = dim.get("dimension")
                if dim_name:
                    acc_by_dim[dim_name] = dim  # latest run wins
            acc_scores = [
                s for s in (_parse_numeric_score(d.get("overallScore")) for d in acc_by_dim.values())
                if s is not None
            ]
            acc_grades = [d.get("overallGrade") for d in acc_by_dim.values() if d.get("overallGrade")]
            trend.append(
                {
                    "runId": item.run_id,
                    "dateISO": item.date_iso,
                    "dateLabel": item.date_label,
                    "dimensionsCount": len(acc_by_dim),
                    "overallGrade": _most_frequent_grade(acc_grades) if acc_grades else None,
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

        runs = [entry.name for entry in _safe_read_dir(project_path) if entry.is_dir() and entry.name.isdigit()]
        runs.sort(reverse=True)
        if as_of:
            runs = [run_id for run_id in runs if run_id <= as_of]
        if not runs:
            return None

        # Pre-read all run data once to avoid redundant disk reads across the loops below.
        all_run_data: dict[str, list[dict[str, Any]]] = {}
        latest_by_dimension: dict[str, dict[str, Any]] = {}
        for run_id in runs:
            dims = _read_run_data(reports_root, project, run_id)
            all_run_data[run_id] = dims
            for dim in dims:
                dim_name = dim.get("dimension")
                if dim_name and dim_name not in latest_by_dimension:
                    latest_by_dimension[dim_name] = {**dim, "fromRunId": run_id}

        all_dimensions = list(latest_by_dimension.values())

        dimensions_with_trend = []
        for dim in all_dimensions:
            from_run = dim.get("fromRunId")
            dim_name = dim.get("dimension")
            previous = None
            if from_run:
                for rid in sorted((r for r in runs if r < from_run), reverse=True):
                    d = next((x for x in all_run_data.get(rid, []) if x.get("dimension") == dim_name), None)
                    if d:
                        previous = {"runId": rid, "dimension": d}
                        break
            trend = _calculate_trend(dim.get("overallScore"), previous.get("dimension", {}).get("overallScore") if previous else None)
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

        numeric_scores = [score for score in (_parse_numeric_score(s) for s in scores) if score is not None]
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
            prev_numeric_scores = [s for s in (_parse_numeric_score(s) for s in prev_scores_raw) if s is not None]
            prev_avg_score = round(sum(prev_numeric_scores) / len(prev_numeric_scores), 1) if prev_numeric_scores else None

        return {
            "project": project,
            "dimensions": dimensions_with_trend,
            "summary": {
                "overallGrade": _most_frequent_grade(grades),
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
            return _parse_eval_from_json(eval_path, project, run_id, dimension)
        markdown_path = base / "evaluation" / f"{dimension}_eval.md"
        if markdown_path.exists():
            try:
                content = markdown_path.read_text()
            except OSError:
                return None
            return _parse_eval_markdown(content, project, run_id, dimension)
        evidence_path = base / "evidence" / f"{dimension}_evidence.json"
        if evidence_path.exists():
            return _parse_violations_from_evidence(evidence_path, project, run_id, dimension)
        stream_path = base / "evidence" / f"{dimension}_live.stream"
        if stream_path.exists():
            return _parse_violations_from_stream(stream_path, project, run_id, dimension)
        return None

    def start_evaluation(self, repo: str, discipline: str | None, dimensions: str, numerical: bool, reports_dir: str, ai_cmd: str | None = None, ai_model: str | None = None):
        repo_path = Path(repo)
        if not is_repo_url(repo) and not repo_path.exists():
            raise FileNotFoundError(f"Repository not found: {repo}")

        reports_abs = str(Path(reports_dir).resolve())
        cmd = [sys.executable, "-m", "codecompass.cli", "evaluate"]
        cmd += ["--evaluations", reports_abs]
        if dimensions:
            cmd += ["-d", dimensions]
        if numerical:
            cmd.append("-n")
        if discipline:
            cmd.append(discipline)
        if is_repo_url(repo):
            cmd.append(repo)
        else:
            cmd.append(str(repo_path.resolve()))

        info = _build_repository_info(repo, discipline)
        info_dir = Path(reports_dir) / str(info["name"])
        info_dir.mkdir(parents=True, exist_ok=True)
        (info_dir / "repository_info.json").write_text(json.dumps(info))

        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if ai_cmd:
            env["AI_CMD"] = ai_cmd
        if ai_model:
            env["AI_MODEL"] = ai_model

        cwd = str(Path.cwd()) if is_repo_url(repo) else str(repo_path.resolve())
        return self._jobs.start_job(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str):
        return self._jobs.get_job(job_id)

    def cancel_evaluation(self, job_id: str) -> bool:
        return self._jobs.cancel_job(job_id)

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
                if violation.get("severity") == "critical":
                    entry["critical"] += 1
                elif violation.get("severity") == "major":
                    entry["major"] += 1
                elif violation.get("severity") == "minor":
                    entry["minor"] += 1

        files = sorted(summary["byFile"].values(), key=lambda item: item["count"], reverse=True)[:20]
        summary["files"] = files
        summary.pop("byFile", None)
        return summary

    def get_ai_clients(self):
        candidates = [
            {"id": "claude", "label": "Claude"},
            {"id": "codex", "label": "Codex"},
            {"id": "copilot", "label": "Copilot"},
        ]
        return {"clients": [c for c in candidates if shutil.which(c["id"])]}

    def get_client_models(self, client_id: str):
        if client_id == "claude":
            return self._get_claude_models()
        if not shutil.which(client_id):
            return {"models": []}
        try:
            result = subprocess.run(
                [client_id, "/models"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            output = result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, OSError):
            return {"models": []}
        models = []
        for line in output.splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and token[0] not in ("#", "=", "-", "[", "("):
                models.append(token)
        return {"models": models}

    def _get_claude_models(self):
        # Try direct API call when ANTHROPIC_API_KEY is available
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                models = [m["id"] for m in data.get("data", []) if m.get("id")]
                if models:
                    return {"models": models}
            except Exception:
                pass
        # Fall back to a curated list of current models.
        # Claude Code uses OAuth (web login) — there's no way to call /v1/models
        # without an API key, so we maintain this list manually.
        return {"models": [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]}

    def browse_repo(self, path: str | None):
        target = Path(path) if path else Path.home()
        target = target.resolve()
        if not target.exists():
            return {"error": "Path not found", "path": str(target)}
        if not target.is_dir():
            return {"error": "Path is not a directory", "path": str(target)}

        directories = []
        for entry in _safe_read_dir(target):
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                continue
            entry_path = target / entry.name
            try:
                os.access(entry_path, os.R_OK)
            except OSError:
                continue
            directories.append(
                {
                    "name": entry.name,
                    "path": str(entry_path),
                    "isGitRepo": (entry_path / ".git").exists(),
                }
            )

        directories.sort(key=lambda item: item["name"])
        parent = target.parent if target.parent != target else None
        return {
            "current": str(target),
            "parent": str(parent) if parent else None,
            "directories": directories,
            "isGitRepo": (target / ".git").exists(),
        }
