"""Prompt assembly for the direct API runner.

Loads api_prompt.md template and fills in source files, standards,
and evaluation rules.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.analysis.prompts._template import load_template
from quodeq.config.prompt_templates import render_template

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


def _read_file_safe(path: Path) -> str | None:
    """Read a file, returning None on failure."""
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        _log.warning("Could not read file: %s", path)
        return None


def _build_files_block(source_files: list[Path], repo_root: Path | None = None) -> str:
    """Build the source files block for the prompt."""
    parts: list[str] = []
    for path in source_files:
        content = _read_file_safe(path)
        if content is None:
            continue
        display_path = str(path.relative_to(repo_root)) if repo_root else path.name
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(content.splitlines()))
        parts.append(f"### {display_path}\n```\n{numbered}\n```")
    return "\n\n".join(parts)


def assemble_api_prompt(
    *,
    source_files: list[Path],
    standards_text: str,
    dimension: str,
    repo_name: str,
    repo_root: Path | None = None,
) -> str:
    """Assemble a complete evaluation prompt for the API runner."""
    template = load_template(template_name="api_prompt.md")
    rules = load_template(template_name="evaluation_rules.md")
    files_block = _build_files_block(source_files, repo_root=repo_root)
    return render_template(template, {
        "DIMENSION": dimension,
        "REPO_NAME": repo_name,
        "STANDARDS_TEXT": standards_text,
        "EVALUATION_RULES": rules,
        "FINDING_SCHEMA": _FINDING_SCHEMA,
        "FILES_BLOCK": files_block,
    })
