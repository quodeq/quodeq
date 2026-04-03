"""Code enrichment: reads source files and fills snippet/context on findings.

Extracted from FindingsRouter to keep module sizes small.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

CONTEXT_LINES = 5


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
        source_lines = read_file(full_path).splitlines()
    except (OSError, UnicodeDecodeError):
        finding.setdefault("snippet", "")
        finding.setdefault("context", "")
        return

    line = finding.get("line", 0)
    scope = finding.get("scope")

    # Scope-level or line=0: store full file in snippet for expand-on-click
    if scope or not line:
        finding["snippet"] = "\n".join(source_lines)
        finding["scope"] = scope or "file"
        finding["context"] = None
        return

    # Normal line-level enrichment
    end_line = finding.get("end_line") or line
    if end_line < line:
        line, end_line = end_line, line
    # Clamp to file boundaries (1-indexed)
    line = max(1, min(line, len(source_lines)))
    end_line = max(line, min(end_line, len(source_lines)))

    # Build snippet (the offending lines)
    snippet_lines = source_lines[line - 1:end_line]
    finding["snippet"] = "\n".join(snippet_lines)

    # Build context with >>> markers
    ctx_start = max(0, line - 1 - CONTEXT_LINES)
    ctx_end = min(len(source_lines), end_line + CONTEXT_LINES)
    context_parts = []
    for i in range(ctx_start, ctx_end):
        prefix = ">>> " if line - 1 <= i < end_line else ""
        context_parts.append(f"{prefix}{source_lines[i]}")
    finding["context"] = "\n".join(context_parts)
