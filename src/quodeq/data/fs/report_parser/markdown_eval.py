"""Markdown evaluation report parsing — converts executive summary tables to structured dicts."""

from __future__ import annotations

import re
from typing import Any

from quodeq.data.fs.report_parser.grades import parse_numeric_score
from quodeq.data.fs.report_parser.json_parser import empty_severity_buckets
from quodeq.data.fs.report_parser.markdown_table import (
    extract_exec_summary,
    is_divider_row,
    split_table_row,
)
from quodeq.core.scoring.internals import score_to_grade_label

_GRADE_SCORE_RE = re.compile(r"^(\d+(?:\.\d+)?/10)(?:\s+(\w+))?$")
_MIN_HEADER_COLS = 4
_MIN_DATA_COLS = 3
_SKIP_ROW_COLS = 2


def _parse_grade_and_score(cells: list[str], is_four_col: bool) -> tuple[str | None, float | None]:
    """Extract grade and score from table row cells."""
    score = None
    grade = None
    if is_four_col:
        raw = cells[-1]
        match = _GRADE_SCORE_RE.match(raw)
        if match:
            score = match.group(1)
            grade = match.group(2)
        else:
            score = raw
    elif len(cells) >= _MIN_DATA_COLS:
        score = cells[1]
        grade = cells[2]
    else:
        grade = cells[1]
    if not grade and score:
        grade_score = parse_numeric_score(score)
        if grade_score is not None:
            grade = score_to_grade_label(grade_score)
    return grade, score


def parse_eval_markdown(markdown: str, project: str, run_id: str, dimension: str) -> dict[str, Any]:
    """Parse a markdown evaluation report into a structured dict with principle grades."""
    table_lines = [line for line in extract_exec_summary(markdown) if not is_divider_row(line)]
    principle_grades: list[dict[str, Any]] = []
    if len(table_lines) >= 2:
        header_cells = [c for c in split_table_row(table_lines[0]) if c]
        is_four_col = len(header_cells) >= _MIN_HEADER_COLS
        for line in table_lines[1:]:
            cells = [c for c in split_table_row(line) if c]
            if len(cells) < _SKIP_ROW_COLS:
                continue
            principle = cells[0]
            grade, score = _parse_grade_and_score(cells, is_four_col)
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
        "priorityRemediation": empty_severity_buckets(),
        "rawContent": markdown,
    }
