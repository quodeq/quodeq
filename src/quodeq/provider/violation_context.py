"""Shared data class and helpers for violation/compliance parsing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ViolationContext:
    """Shared context for violation/compliance parsing."""
    project: str
    run_id: str
    dimension: str


def build_finding_base(
    *,
    principle: str | None,
    file: str | None = None,
    line: int | str | None = None,
    title: str | None = None,
    reason: str | None = None,
    snippet: str | None = None,
    severity: str | None = None,
    cwe: int | str | None = None,
    include_severity: bool = True,
) -> dict[str, Any]:
    """Build the core fields shared by all finding/violation normalizers.

    Used by both ``violations_parsing`` (JSONL/stream) and ``json_parser``
    (evaluation JSON) to avoid duplicating the same field assembly (CWE-1041).
    """
    entry: dict[str, Any] = {
        "principle": principle,
        "file": file,
        "line": line,
        "title": title,
        "reason": reason,
        "snippet": snippet,
    }
    if include_severity:
        entry["severity"] = severity or "minor"
    if cwe:
        entry["cwe"] = cwe
    return entry


def format_file_line(file: str | None, line: int | str | None) -> str | None:
    """Format a ``file:line`` string, returning *file* alone when *line* is absent."""
    if file and line:
        return f"{file}:{line}"
    return file
