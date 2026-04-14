"""Code enrichment: reads source files and fills snippet/context on findings.

Extracted from FindingsRouter to keep module sizes small.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

CONTEXT_LINES = 5
_MAX_SNIPPET_LINES = 40  # cap for scope-level snippets


def _extract_window(source: str, line: int, end_line: int, context: int) -> list[str]:
    """Extract a bounded window of lines from *source* around [line, end_line].

    Only splits and retains the lines within the window instead of keeping
    the full splitlines() list alive.  *line* and *end_line* are 1-indexed.
    """
    win_start = max(0, line - 1 - context)  # 0-indexed
    win_end = end_line + context  # exclusive
    # Split lazily by iterating; stop once we've passed the window.
    result: list[str] = []
    idx = 0
    start = 0
    while start <= len(source):
        end = source.find("\n", start)
        if end == -1:
            end = len(source)
            if idx >= win_start:
                result.append(source[start:end])
            break
        if idx >= win_start:
            result.append(source[start:end])
        idx += 1
        start = end + 1
        if idx >= win_end:
            break
    return result


def _enrich_line_level(
    finding: dict, source: str, line: int,
) -> None:
    """Fill snippet and context for a line-level finding."""
    end_line = finding.get("end_line") or line
    if end_line < line:
        line, end_line = end_line, line

    window = _extract_window(source, line, end_line, CONTEXT_LINES)
    if not window:
        finding.setdefault("snippet", "")
        finding.setdefault("context", "")
        return

    win_start_1 = max(1, line - CONTEXT_LINES)  # 1-indexed start of window
    snippet_parts: list[str] = []
    context_parts: list[str] = []
    for i, text in enumerate(window):
        lno = win_start_1 + i
        if line <= lno <= end_line:
            snippet_parts.append(text)
            context_parts.append(f">>> {text}")
        else:
            context_parts.append(text)
    finding["snippet"] = "\n".join(snippet_parts)
    finding["context"] = "\n".join(context_parts)


def enrich_code(
    finding: dict,
    work_dir: Path | None,
    read_file: Callable[[Path], str],
) -> None:
    """Fill snippet and context by reading the source file from *work_dir*."""
    if work_dir is None:
        return
    file_path = finding.get("file")
    if not file_path:
        return
    try:
        full_path = work_dir / file_path
        # Path containment check: prevent traversal outside the work directory.
        if not full_path.resolve().is_relative_to(work_dir.resolve()):
            finding.setdefault("snippet", "")
            finding.setdefault("context", "")
            return
        source = read_file(full_path)
    except (OSError, UnicodeDecodeError):
        finding.setdefault("snippet", "")
        finding.setdefault("context", "")
        return

    line = finding.get("line", 0)
    scope = finding.get("scope")

    # Scope-level or line=0: store capped snippet for expand-on-click
    if scope or not line:
        # Cap at _MAX_SNIPPET_LINES to avoid storing huge files in memory
        lines = source.split("\n", _MAX_SNIPPET_LINES + 1)
        if len(lines) > _MAX_SNIPPET_LINES:
            lines = lines[:_MAX_SNIPPET_LINES]
        finding["snippet"] = "\n".join(lines)
        finding["scope"] = scope or "file"
        finding["context"] = None
        return

    _enrich_line_level(finding, source, line)
