from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from codecompass.action_provider import ActionProvider
from codecompass.action_provider_jobs import JobManager
from codecompass.evaluate.lib.repo_handler import is_repo_url


NUMERIC_GRADE_ORDER = ["Critical", "Poor", "Adequate", "Good", "Exemplary"]
TEXT_GRADE_ORDER = ["Insufficient", "Developing", "Proficient", "Exemplary"]
SEVERITIES = {"critical", "major", "minor", "unknown"}


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    date_iso: str | None
    date_label: str


def _safe_read_dir(path: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _parse_run_id_date(run_id: str) -> tuple[str | None, str]:
    match = None
    if len(run_id) >= 8 and run_id[:8].isdigit():
        match = run_id[:8]
    if not match:
        return None, run_id
    try:
        parsed = datetime.strptime(match, "%Y%m%d")
    except ValueError:
        return None, run_id
    return parsed.date().isoformat(), parsed.strftime("%b %d, %Y")


def _parse_numeric_score(score_text: str | None) -> float | None:
    if not score_text:
        return None
    import re

    match = re.search(r"(\d+(?:\.\d+)?)", str(score_text))
    if not match:
        return None
    return float(match.group(1))


def _clean_cell(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


def _build_repository_info(repo: str, discipline: str | None) -> dict[str, str | None]:
    if is_repo_url(repo):
        name = repo.split("/")[-1].replace(".git", "")
        return {
            "name": name,
            "discipline": discipline,
            "location": "online",
            "path": repo,
        }
    resolved = Path(repo).resolve()
    return {
        "name": resolved.name,
        "discipline": discipline,
        "location": "local",
        "path": str(resolved),
    }


def _split_table_row(line: str) -> list[str]:
    raw = line.strip()
    no_outer = raw.lstrip("|").rstrip("|")
    return [_clean_cell(cell) for cell in no_outer.split("|")]


def _is_divider_row(line: str) -> bool:
    import re

    return re.match(r"^\s*\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$", line) is not None


def _extract_exec_summary(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == "## executive summary":
            start = idx
            break
    if start < 0:
        return []
    result = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("## "):
            break
        if "|" in line:
            result.append(line)
    return result


def _parse_eval_markdown(markdown: str, project: str, run_id: str, dimension: str) -> dict[str, Any]:
    table_lines = [line for line in _extract_exec_summary(markdown) if not _is_divider_row(line)]
    principle_grades: list[dict[str, Any]] = []
    if len(table_lines) >= 2:
        header_cells = [c for c in _split_table_row(table_lines[0]) if c]
        is_four_col = len(header_cells) >= 4
        for line in table_lines[1:]:
            cells = [c for c in _split_table_row(line) if c]
            if len(cells) < 2:
                continue
            principle = cells[0]
            score = None
            grade = None
            if is_four_col:
                raw = cells[-1]
                import re

                match = re.match(r"^(\d+(?:\.\d+)?/10)(?:\s+(\w+))?$", raw)
                if match:
                    score = match.group(1)
                    grade = match.group(2)
                else:
                    score = raw
            elif len(cells) >= 3:
                score = cells[1]
                grade = cells[2]
            else:
                grade = cells[1]
            if not grade and score:
                grade_score = _parse_numeric_score(score)
                if grade_score is not None:
                    if grade_score >= 9:
                        grade = "Exemplary"
                    elif grade_score >= 7:
                        grade = "Good"
                    elif grade_score >= 5:
                        grade = "Adequate"
                    elif grade_score >= 3:
                        grade = "Poor"
                    else:
                        grade = "Critical"
            is_overall = "overall" in principle.lower()
            principle_grades.append(
                {
                    "principle": principle,
                    "score": score,
                    "grade": grade,
                    "isOverall": is_overall,
                }
            )

    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "principleGrades": principle_grades,
        "principles": [],
        "priorityRemediation": {"critical": [], "major": [], "minor": []},
        "rawContent": markdown,
    }


def _most_frequent_grade(grades: list[str]) -> str | None:
    if not grades:
        return None
    counts: dict[str, int] = {}
    for grade in grades:
        counts[grade] = counts.get(grade, 0) + 1
    winner = grades[0]
    winner_count = counts[winner]
    for grade, count in counts.items():
        if count > winner_count:
            winner = grade
            winner_count = count
            continue
        if count == winner_count:
            if grade in NUMERIC_GRADE_ORDER and winner in NUMERIC_GRADE_ORDER:
                if NUMERIC_GRADE_ORDER.index(grade) > NUMERIC_GRADE_ORDER.index(winner):
                    winner = grade
                    continue
            if grade in TEXT_GRADE_ORDER and winner in TEXT_GRADE_ORDER:
                if TEXT_GRADE_ORDER.index(grade) > TEXT_GRADE_ORDER.index(winner):
                    winner = grade
    return winner


def _build_totals(violations: list[dict[str, Any]], compliance: list[dict[str, Any]]) -> dict[str, Any]:
    severity = {"critical": 0, "major": 0, "minor": 0, "unknown": 0}
    for entry in violations:
        key = entry.get("severity", "unknown")
        if key not in SEVERITIES:
            key = "unknown"
        severity[key] += 1
    return {
        "violationCount": len(violations),
        "complianceCount": len(compliance),
        "severity": severity,
    }


def _parse_report_json(json_path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(json_path.read_text())
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    violations = [
        {
            "principle": v.get("principle"),
            "file": v.get("file"),
            "line": v.get("line"),
            "reason": v.get("reason"),
            "severity": v.get("severity", "minor"),
            "snippet": v.get("snippet"),
        }
        for v in data.get("violations", [])
    ]
    compliance = [
        {
            "principle": c.get("principle"),
            "file": c.get("file"),
            "line": c.get("line"),
            "reason": c.get("reason"),
            "snippet": c.get("snippet"),
        }
        for c in data.get("compliance", [])
    ]

    return {
        "dimension": data.get("dimension"),
        "overallScore": data.get("overallScore"),
        "overallGrade": data.get("overallGrade"),
        "principles": [
            {"name": p.get("name"), "score": p.get("score"), "grade": p.get("grade")}
            for p in data.get("principles", [])
        ],
        "detailPrinciples": [],
        "violations": violations,
        "compliance": compliance,
        "totals": _build_totals(violations, compliance),
    }


def _parse_evidence_file(evidence_path: Path) -> dict[str, Any]:
    dimension = evidence_path.name.replace("_evidence.json", "")
    try:
        data = json.loads(evidence_path.read_text())
    except OSError:
        data = {}
    except json.JSONDecodeError:
        data = {}
    return {
        "dimension": dimension,
        "sourceFileCount": data.get("source_file_count"),
        "date": data.get("date"),
        "discipline": data.get("discipline"),
    }


def _summarize_dimensions(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    overall_grades = [d.get("overallGrade") for d in dimensions if d.get("overallGrade")]
    numeric_scores = [
        score for score in (_parse_numeric_score(d.get("overallScore")) for d in dimensions) if score is not None
    ]
    numeric_average = None
    if numeric_scores:
        numeric_average = round(sum(numeric_scores) / len(numeric_scores), 1)

    grade_breakdown: dict[str, int] = {}
    for grade in overall_grades:
        grade_breakdown[grade] = grade_breakdown.get(grade, 0) + 1

    return {
        "dimensionsCount": len(dimensions),
        "overallGrade": _most_frequent_grade(overall_grades),
        "numericAverage": numeric_average,
        "gradeBreakdown": [
            {"grade": grade, "count": count}
            for grade, count in sorted(grade_breakdown.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _read_run_data(reports_root: Path, project: str, run_id: str) -> list[dict[str, Any]]:
    run_dir = reports_root / project / run_id
    evaluation_dir = run_dir / "evaluation"
    evidence_dir = run_dir / "evidence"

    evaluations: list[dict[str, Any]] = []
    seen_dimensions: set[str] = set()
    entries = _safe_read_dir(evaluation_dir)
    for entry in entries:
        if not entry.is_file() or not entry.name.endswith("_eval.md"):
            continue
        dimension = entry.name[:-8]
        json_path = evaluation_dir / f"{dimension}.json"
        parsed = _parse_report_json(json_path) if json_path.exists() else None
        if parsed:
            evaluations.append(parsed)
            seen_dimensions.add(dimension)

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        dimension = entry.name[:-5]
        if dimension in seen_dimensions:
            continue
        parsed = _parse_report_json(Path(entry.path))
        if parsed:
            evaluations.append(parsed)
            seen_dimensions.add(dimension)

    evidence_map: dict[str, dict[str, Any]] = {}
    for entry in _safe_read_dir(evidence_dir):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            parsed = _parse_evidence_file(Path(entry.path))
            evidence_map[parsed["dimension"]] = parsed

    dimensions = []
    for evaluation in evaluations:
        dimension = evaluation.get("dimension")
        evidence = evidence_map.get(dimension, {})
        dimensions.append(
            {
                **evaluation,
                "sourceFileCount": evidence.get("sourceFileCount"),
                "evidenceDate": evidence.get("date"),
                "discipline": evidence.get("discipline"),
            }
        )

    dimensions.sort(key=lambda item: item.get("dimension") or "")
    return dimensions


def _list_runs(reports_root: Path, project: str) -> list[RunInfo]:
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in _safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        date_iso, date_label = _parse_run_id_date(entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    return run_infos


def _calculate_trend(current_score: Any, previous_score: Any) -> str:
    current = _parse_numeric_score(str(current_score)) if current_score is not None else None
    previous = _parse_numeric_score(str(previous_score)) if previous_score is not None else None
    if current is None or previous is None:
        return "none"
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "same"


def _get_previous_run_for_dimension(reports_root: Path, project: str, current_run_id: str, dimension: str) -> dict[str, Any] | None:
    project_path = reports_root / project
    if not project_path.exists():
        return None
    runs = [entry.name for entry in _safe_read_dir(project_path) if entry.is_dir() and entry.name < current_run_id]
    runs.sort(reverse=True)
    for run_id in runs:
        dimensions = _read_run_data(reports_root, project, run_id)
        dim = next((d for d in dimensions if d.get("dimension") == dimension), None)
        if dim:
            return {"runId": run_id, "dimension": dim}
    return None


def _parse_eval_from_json(json_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        data = json.loads(json_path.read_text())
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    principle_grades = [
        {
            "principle": p.get("name"),
            "score": p.get("score"),
            "grade": p.get("grade"),
            "isOverall": False,
        }
        for p in data.get("principles", [])
    ]
    principle_grades.append(
        {
            "principle": "Overall",
            "score": data.get("overallScore"),
            "grade": data.get("overallGrade"),
            "isOverall": True,
        }
    )

    # Build per-principle detail by grouping top-level violations and compliance
    principle_map: dict[str, Any] = {}
    for p in data.get("principles", []):
        name = p.get("name", "")
        principle_map[name] = {
            "name": name,
            "score": p.get("score"),
            "grade": p.get("grade"),
            "violations": [],
            "compliance": [],
            "justification": "",
            "recommendations": [],
            "metrics": None,
        }
    for v in data.get("violations", []):
        key = v.get("principle", "")
        if key not in principle_map:
            principle_map[key] = {"name": key, "score": None, "grade": None, "violations": [], "compliance": [], "justification": "", "recommendations": [], "metrics": None}
        f = v.get("file")
        line = v.get("line")
        principle_map[key]["violations"].append({
            "code": v.get("snippet", ""),
            "severity": v.get("severity", "minor"),
            "file": f"{f}:{line}" if f and line else f,
            "reason": v.get("reason", ""),
        })
    for c in data.get("compliance", []):
        key = c.get("principle", "")
        if key not in principle_map:
            principle_map[key] = {"name": key, "score": None, "grade": None, "violations": [], "compliance": [], "justification": "", "recommendations": [], "metrics": None}
        principle_map[key]["compliance"].append(c.get("snippet") or c.get("reason") or "")

    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "principleGrades": principle_grades,
        "principles": list(principle_map.values()),
        "violations": data.get("violations", []),
        "compliance": data.get("compliance", []),
        "priorityRemediation": {"critical": [], "major": [], "minor": []},
        "rawContent": None,
    }


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

        run_data_cache: dict[int, list[dict[str, Any]]] = {}
        def get_run_dimensions(idx: int) -> list[dict[str, Any]]:
            if idx not in run_data_cache:
                run_data_cache[idx] = _read_run_data(reports_root, project, runs[idx].run_id)
            return run_data_cache[idx]

        non_na_count: dict[str, int] = {}
        stale_previous_by_dimension: dict[str, dict[str, Any]] = {}

        for i in range(selected_index + 1, len(runs)):
            run_dimensions = get_run_dimensions(i)
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
            run_dimensions = get_run_dimensions(i)
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

        trend = []
        for item in runs:
            dimensions = _read_run_data(reports_root, project, item.run_id)
            summary = _summarize_dimensions(dimensions)
            trend.append(
                {
                    "runId": item.run_id,
                    "dateISO": item.date_iso,
                    "dateLabel": item.date_label,
                    "dimensionsCount": summary.get("dimensionsCount"),
                    "overallGrade": summary.get("overallGrade"),
                    "numericAverage": summary.get("numericAverage"),
                }
            )

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

        latest_by_dimension: dict[str, dict[str, Any]] = {}
        for run_id in runs:
            dimensions = _read_run_data(reports_root, project, run_id)
            for dim in dimensions:
                dim_name = dim.get("dimension")
                if dim_name and dim_name not in latest_by_dimension:
                    latest_by_dimension[dim_name] = {**dim, "fromRunId": run_id}

        all_dimensions = list(latest_by_dimension.values())

        dimensions_with_trend = []
        for dim in all_dimensions:
            previous = _get_previous_run_for_dimension(reports_root, project, dim.get("fromRunId"), dim.get("dimension"))
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

        return {
            "project": project,
            "dimensions": dimensions_with_trend,
            "summary": {
                "overallGrade": _most_frequent_grade(grades),
                "numericAverage": avg_score,
                "totalViolations": total_violations,
                "totalCompliance": total_compliance,
                "dimensionCount": len(dimensions_with_trend),
                "severity": {"critical": critical, "major": major, "minor": minor},
            },
        }

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str):
        eval_path = Path(reports_dir) / project / run_id / "evaluation" / f"{dimension}.json"
        if eval_path.exists():
            return _parse_eval_from_json(eval_path, project, run_id, dimension)
        markdown_path = Path(reports_dir) / project / run_id / "evaluation" / f"{dimension}_eval.md"
        if markdown_path.exists():
            try:
                content = markdown_path.read_text()
            except OSError:
                return None
            return _parse_eval_markdown(content, project, run_id, dimension)
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
        import subprocess
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
        import json
        import urllib.request
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
