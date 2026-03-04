from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from codecompass.evaluate.lib.repo_handler import is_repo_url


NUMERIC_GRADE_ORDER = ["Critical", "Poor", "Adequate", "Good", "Exemplary"]
TEXT_GRADE_ORDER = ["Insufficient", "Developing", "Proficient", "Exemplary"]
SEVERITIES = {"critical", "major", "minor", "unknown"}


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    date_iso: str | None
    date_label: str


def safe_read_dir(path: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            return list(it)
    except OSError:
        return []


def _normalize_date(raw: str) -> tuple[str, str] | None:
    """Parse a date/datetime string and return (sortable_iso, human_label).

    Accepts ISO datetime (2026-03-01T14:30:25), ISO date (2026-03-01),
    or compact date (20260301).  The first element is the full string
    (including time when available) so that same-day runs sort correctly.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            sortable = parsed.isoformat(timespec='seconds') if "T" in fmt else parsed.date().isoformat()
            label = parsed.strftime("%b %d, %Y")
            return sortable, label
        except ValueError:
            continue
    return None


def _parse_run_date(reports_root: Path, project: str, run_id: str) -> tuple[str | None, str]:
    """Read the date from the first evidence file in a run directory."""
    evidence_dir = reports_root / project / run_id / "evidence"
    for entry in safe_read_dir(evidence_dir):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            try:
                data = json.loads(Path(entry.path).read_text())
                raw = data.get("date")
                if raw:
                    result = _normalize_date(str(raw))
                    if result:
                        return result
            except (json.JSONDecodeError, OSError):
                pass
    # Fallback: try parsing the run_id itself as a date (backward compat with YYYYMMDD dirs)
    fallback = _normalize_date(run_id)
    if fallback:
        return fallback
    return None, run_id


def parse_numeric_score(score_text: str | None) -> float | None:
    if not score_text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(score_text))
    if not match:
        return None
    return float(match.group(1))


def clean_cell(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


def build_repository_info(repo: str, discipline: str | None) -> dict[str, str | None]:
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


def split_table_row(line: str) -> list[str]:
    raw = line.strip()
    no_outer = raw.lstrip("|").rstrip("|")
    return [clean_cell(cell) for cell in no_outer.split("|")]


def is_divider_row(line: str) -> bool:
    return re.match(r"^\s*\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$", line) is not None


def extract_exec_summary(markdown: str) -> list[str]:
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


def parse_eval_markdown(markdown: str, project: str, run_id: str, dimension: str) -> dict[str, Any]:
    table_lines = [line for line in extract_exec_summary(markdown) if not is_divider_row(line)]
    principle_grades: list[dict[str, Any]] = []
    if len(table_lines) >= 2:
        header_cells = [c for c in split_table_row(table_lines[0]) if c]
        is_four_col = len(header_cells) >= 4
        for line in table_lines[1:]:
            cells = [c for c in split_table_row(line) if c]
            if len(cells) < 2:
                continue
            principle = cells[0]
            score = None
            grade = None
            if is_four_col:
                raw = cells[-1]
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
                grade_score = parse_numeric_score(score)
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


def most_frequent_grade(grades: list[str]) -> str | None:
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


def build_totals(violations: list[dict[str, Any]], compliance: list[dict[str, Any]]) -> dict[str, Any]:
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


def parse_report_json(json_path: Path) -> dict[str, Any] | None:
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
        "totals": build_totals(violations, compliance),
    }


def parse_evidence_file(evidence_path: Path) -> dict[str, Any]:
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


def summarize_dimensions(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    overall_grades = [d.get("overallGrade") for d in dimensions if d.get("overallGrade")]
    numeric_scores = [
        score for score in (parse_numeric_score(d.get("overallScore")) for d in dimensions) if score is not None
    ]
    numeric_average = None
    if numeric_scores:
        numeric_average = round(sum(numeric_scores) / len(numeric_scores), 1)

    grade_breakdown: dict[str, int] = {}
    for grade in overall_grades:
        grade_breakdown[grade] = grade_breakdown.get(grade, 0) + 1

    return {
        "dimensionsCount": len(dimensions),
        "overallGrade": most_frequent_grade(overall_grades),
        "numericAverage": numeric_average,
        "gradeBreakdown": [
            {"grade": grade, "count": count}
            for grade, count in sorted(grade_breakdown.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def read_run_data(reports_root: Path, project: str, run_id: str) -> list[dict[str, Any]]:
    run_dir = reports_root / project / run_id
    evaluation_dir = run_dir / "evaluation"
    evidence_dir = run_dir / "evidence"

    evaluations: list[dict[str, Any]] = []
    seen_dimensions: set[str] = set()
    entries = safe_read_dir(evaluation_dir)
    for entry in entries:
        if not entry.is_file() or not entry.name.endswith("_eval.md"):
            continue
        dimension = entry.name[:-8]
        json_path = evaluation_dir / f"{dimension}.json"
        parsed = parse_report_json(json_path) if json_path.exists() else None
        if parsed:
            evaluations.append(parsed)
            seen_dimensions.add(dimension)

    for entry in entries:
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        dimension = entry.name[:-5]
        if dimension in seen_dimensions:
            continue
        parsed = parse_report_json(Path(entry.path))
        if parsed:
            evaluations.append(parsed)
            seen_dimensions.add(dimension)

    evidence_map: dict[str, dict[str, Any]] = {}
    for entry in safe_read_dir(evidence_dir):
        if entry.is_file() and entry.name.endswith("_evidence.json"):
            parsed = parse_evidence_file(Path(entry.path))
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


def list_runs(reports_root: Path, project: str) -> list[RunInfo]:
    project_dir = reports_root / project
    run_infos: list[RunInfo] = []
    for entry in safe_read_dir(project_dir):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        # Skip repository_info.json-only dirs (the project root itself won't have sub-runs)
        date_iso, date_label = _parse_run_date(reports_root, project, entry.name)
        run_infos.append(RunInfo(run_id=entry.name, date_iso=date_iso, date_label=date_label))
    run_infos.sort(key=lambda r: (r.date_iso or "", r.run_id), reverse=True)
    return run_infos


def calculate_trend(current_score: Any, previous_score: Any) -> str:
    current = parse_numeric_score(str(current_score)) if current_score is not None else None
    previous = parse_numeric_score(str(previous_score)) if previous_score is not None else None
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
    all_runs = list_runs(reports_root, project)
    # Find the index of the current run, then iterate older runs (after it in the sorted list)
    current_idx = next((i for i, r in enumerate(all_runs) if r.run_id == current_run_id), -1)
    if current_idx < 0:
        return None
    for run_info in all_runs[current_idx + 1:]:
        dimensions = read_run_data(reports_root, project, run_info.run_id)
        dim = next((d for d in dimensions if d.get("dimension") == dimension), None)
        if dim:
            return {"runId": run_info.run_id, "dimension": dim}
    return None


def parse_eval_from_json(json_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
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
