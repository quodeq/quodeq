"""Prompt assembly for the direct API runner.

Bundles source files, standards, and evaluation instructions into a single
prompt that requests structured JSON output matching the JSONL evidence schema.
"""
from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_FINDING_SCHEMA = """\
Each finding must be a JSON object with these fields:
  Required:
    "req": string - requirement ID (e.g. "M-MOD-1", "S-CON-3")
    "t": string - "violation" or "compliance"
    "file": string - file path relative to repo root
    "line": integer - line number
    "severity": string - "critical", "major", or "minor"
    "w": string - short title of the finding
    "reason": string - why this is a violation or compliance
  Optional:
    "end_line": integer - last line if multi-line
    "snippet": string - code snippet
    "scope": string - "file", "class", or "module"
"""

_SYSTEM_TEMPLATE = """\
You are a code quality evaluator. Analyze the provided source code against \
the given standards for the "{dimension}" dimension.

Repository: {repo_name}

## Standards

{standards_text}

## Output Format

Return a JSON object with a single key "findings" containing an array of finding objects.

{schema}

Example:
{{"findings": [{{"req": "M-MOD-1", "t": "violation", "file": "src/app.py", "line": 10, \
"severity": "major", "w": "Multiple responsibilities", "reason": "Module handles both IO and logic"}}]}}

If no findings, return: {{"findings": []}}

## Source Files

{files_block}

Analyze these files for the "{dimension}" dimension only. \
Report violations and notable compliance. Be precise with line numbers.
"""


def _read_file_safe(path: Path) -> str | None:
    """Read a file, returning None on failure."""
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        _log.warning("Could not read file: %s", path)
        return None


def _build_files_block(source_files: list[Path]) -> str:
    """Build the source files block for the prompt."""
    parts: list[str] = []
    for path in source_files:
        content = _read_file_safe(path)
        if content is None:
            continue
        parts.append(f"### {path.name}\n```\n{content}\n```")
    return "\n\n".join(parts)


def assemble_api_prompt(
    *,
    source_files: list[Path],
    standards_text: str,
    dimension: str,
    repo_name: str,
) -> str:
    """Assemble a complete evaluation prompt for the API runner."""
    files_block = _build_files_block(source_files)
    return _SYSTEM_TEMPLATE.format(
        dimension=dimension,
        repo_name=repo_name,
        standards_text=standards_text,
        schema=_FINDING_SCHEMA,
        files_block=files_block,
    )
