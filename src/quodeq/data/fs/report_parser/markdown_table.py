"""Markdown table utilities — cell cleaning, row splitting, and section extraction."""

from __future__ import annotations

import re

_DIVIDER_RE = re.compile(r"^\s*\|?\s*[-:]+(\s*\|\s*[-:]+)+\s*\|?\s*$")


def clean_cell(value: str) -> str:
    """Strip bold markers and backticks from a markdown table cell."""
    return value.replace("**", "").replace("`", "").strip()


def split_table_row(line: str) -> list[str]:
    """Split a markdown table row into cleaned cell values."""
    raw = line.strip()
    no_outer = raw.lstrip("|").rstrip("|")
    return [clean_cell(cell) for cell in no_outer.split("|")]


def is_divider_row(line: str) -> bool:
    """Return True if the line is a markdown table divider (dashes and pipes)."""
    return _DIVIDER_RE.match(line) is not None


_EXEC_SUMMARY_HEADER = "## executive summary"
_SECTION_PREFIX = "## "


def extract_exec_summary(markdown: str) -> list[str]:
    """Extract table lines from the '## Executive Summary' section of a markdown report."""
    lines = markdown.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == _EXEC_SUMMARY_HEADER:
            start = idx
            break
    if start < 0:
        return []
    result = []
    for line in lines[start + 1 :]:
        if line.strip().startswith(_SECTION_PREFIX):
            break
        if "|" in line:
            result.append(line)
    return result
