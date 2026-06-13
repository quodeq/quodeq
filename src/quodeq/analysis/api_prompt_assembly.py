"""Prompt assembly for the direct API runner.

Loads api_prompt.md template and fills in source files, standards,
and evaluation rules.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.analysis.prompts._template import load_template
from quodeq.analysis.prompts.builder import _load_evaluation_rules
from quodeq.config.prompt_templates import render_template
from quodeq.context.path_role import Role, path_role
from quodeq.context.project_shape import Deployment, ProjectShape, detect_shape

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
    "reason": string - 1–3 sentences: what the quoted code does wrong AS WRITTEN, plus the concrete impact
    "snippet": string - offending code copied VERBATIM from the source (one or a few contiguous lines, exact characters)
  Optional:
    "end_line": integer - last line if multi-line
    "scope": string - "file", "class", or "module"
    "vt": string - violation type taxonomy code: a short, stable, kebab-case class of the violation (e.g. "code-injection", "hardcoded-secret", "missing-error-handling"); reuse the exact same code for every finding of the same kind
"""


def _read_file_safe(path: Path) -> str | None:
    """Read a file, returning None on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _log.warning("Could not read file: %s", path)
        return None


def _role_label(display_path: str) -> str:
    """Return a `(role: <role>)` suffix for non-prod paths, empty otherwise.

    Tells the LLM the surrounding code's purpose so it can tone down findings
    that don't matter outside production code (e.g. brittle test fixtures).
    """
    role = path_role(display_path)
    if role is Role.PROD:
        return ""
    return f" (role: {role.value})"


def _build_files_block(source_files: list[Path], repo_root: Path | None = None) -> str:
    """Build the source files block for the prompt."""
    parts: list[str] = []
    for path in source_files:
        content = _read_file_safe(path)
        if content is None:
            continue
        # Always emit POSIX-style separators so the LLM sees the same path
        # shape on every host. str(path.relative_to(...)) yields backslashes
        # on Windows, which are unusual in code prompts and inconsistent
        # with the path-role classifier's normalisation.
        display_path = path.relative_to(repo_root).as_posix() if repo_root else path.name
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(content.splitlines()))
        parts.append(f"### {display_path}{_role_label(display_path)}\n```\n{numbered}\n```")
    return "\n\n".join(parts)


def _format_shape_block(shape: ProjectShape) -> str:
    """Render a project-shape briefing for the LLM, or empty when unknown.

    Skipped for ``UNKNOWN`` deployments: the heuristics didn't fire and we
    don't want to plant a wrong assumption in the model's head.
    """
    if shape.deployment is Deployment.UNKNOWN:
        return ""
    parts: list[str] = [f"deployment={shape.deployment.value}",
                        f"single_user={'true' if shape.is_single_user else 'false'}"]
    if shape.runtime_langs:
        parts.append(f"runtime={'+'.join(shape.runtime_langs)}")
    if shape.web_frameworks:
        parts.append(f"web_frameworks={'+'.join(shape.web_frameworks)}")
    if shape.ui_lang:
        parts.append(f"ui={shape.ui_lang}")
    summary = ", ".join(parts)

    note = ""
    if shape.deployment is Deployment.DESKTOP and shape.is_single_user:
        note = (
            " This is a single-user desktop tool, not a hosted multi-tenant"
            " service. Treat findings about thread blocking, distributed"
            " state, concurrent callers, and rate limiting with skepticism."
        )
    elif shape.deployment is Deployment.LIBRARY:
        note = (
            " This is a library, not an end-user application. API stability"
            " and backwards compatibility matter more than user-facing UX."
        )
    elif shape.deployment is Deployment.CLI and shape.is_single_user:
        note = (
            " This is a single-user CLI, not a hosted service. Concurrent"
            " caller and multi-tenant findings rarely apply."
        )
    return f"## Project Shape\n\n**{summary}**.{note}"


def assemble_api_prompt(
    *,
    source_files: list[Path],
    standards_text: str,
    dimension: str,
    repo_name: str,
    repo_root: Path | None = None,
    project_shape: ProjectShape | None = None,
) -> str:
    """Assemble a complete evaluation prompt for the API runner.

    *project_shape* is computed from *repo_root* when not supplied; pass an
    explicit shape to skip detection (e.g. when a cached shape is being
    reused across dimensions).
    """
    template = load_template(template_name="api_prompt.md")
    rules = _load_evaluation_rules()
    files_block = _build_files_block(source_files, repo_root=repo_root)
    if project_shape is None and repo_root is not None:
        project_shape = detect_shape(repo_root)
    shape_block = _format_shape_block(project_shape) if project_shape else ""
    return render_template(template, {
        "DIMENSION": dimension,
        "REPO_NAME": repo_name,
        "STANDARDS_TEXT": standards_text,
        "PROJECT_SHAPE": shape_block,
        "EVALUATION_RULES": rules,
        "FINDING_SCHEMA": _FINDING_SCHEMA,
        "FILES_BLOCK": files_block,
    })
