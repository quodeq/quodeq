from __future__ import annotations

import re
from typing import Any

from quodeq.adapters.fs.report_parser.grades import parse_numeric_score


def clean_cell(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


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
