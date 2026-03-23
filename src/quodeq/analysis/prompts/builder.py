"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.config.paths import default_paths
from quodeq.config.prompt_templates import render_template
from quodeq.shared.utils import read_json

if TYPE_CHECKING:
    from quodeq.analysis.manifest import AnalysisTarget, SourceManifest

_logger = logging.getLogger(__name__)

_NO_GUIDANCE = "_No additional guidance._"
_NO_STANDARDS = "_No compiled standards available._"
_NO_STANDARDS_FOR_DIM = "_No compiled standards for this dimension._"
_STANDARDS_READ_ERROR = "_Could not read compiled standards._"


def _load_dimension_data(compiled_dir: Path, dimension: str) -> dict | None:
    """Load compiled standards JSON for a dimension, or None on error."""
    compiled_file = compiled_dir / f"{dimension}.json"
    if not compiled_file.exists():
        return None
    try:
        return read_json(compiled_file)
    except (OSError, ValueError) as exc:
        _logger.warning("Could not read compiled standards %s: %s", compiled_file, exc)
        return None


def render_compiled_standards(compiled_dir: Path, dimension: str) -> str:
    """Render compiled standards as a requirements checklist organized by principle."""
    data = _load_dimension_data(compiled_dir, dimension)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    lines = []
    for principle in data.get("principles", []):
        reqs = principle.get("requirements", [])
        if not reqs:
            continue
        lines.append(f"### {principle['name']}")
        for req in reqs:
            lines.append(f"- **{req['id']}**: {req['text']}")
        lines.append("")
    return "\n".join(lines)


def render_compact_standards(compiled_dir: Path, dimension: str) -> str:
    """Render a compact standards checklist for the AI analyzer.

    One line per requirement: ``REQ-ID: text``.
    No principle headings (server derives principle from req ID),
    no markdown formatting, no CWE refs (server enriches at report time).
    """
    data = _load_dimension_data(compiled_dir, dimension)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    lines = []
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            lines.append(f"{req['id']}: {req['text']}")
    return "\n".join(lines)


def render_dimensions(dimensions_data: dict, dimension: str) -> str:
    """Format dimension info for prompt inclusion."""
    applies = dimensions_data.get("applies", [])
    dim_entry = next((d for d in applies if d["id"] == dimension), None)

    if not dim_entry:
        return f"_Dimension '{dimension}' not configured._"

    lines = [
        f"**Dimension:** {dimension}",
        f"**Weight:** {dim_entry.get('weight', 1.0)}",
    ]

    iso = dim_entry.get("iso_25010")
    if iso:
        lines.append(f"**ISO 25010:** {iso}")

    source = dim_entry.get("source")
    if source:
        lines.append(f"**Source:** {source}")

    return "\n".join(lines)


def load_template(
    template_path: Path | None = None,
    *,
    prompts_dir: Path | None = None,
    template_name: str = "compass.md",
) -> str:
    """Load a prompt template.

    Args:
        template_path: Explicit path to a template file (takes priority).
        prompts_dir: Directory containing prompt templates; used to locate
            *template_name* when *template_path* is not given.
        template_name: Template filename to load (default ``compass.md``).
    """
    if template_path:
        try:
            return template_path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            raise FileNotFoundError(f"Cannot read template {template_path}: {exc}") from exc
    if prompts_dir is None:
        prompts_dir = default_paths().prompts_dir
    path = prompts_dir / template_name
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot read template {path}: {exc}") from exc


@dataclass
class PromptContext:
    """Parameters for rendering a per-dimension analysis prompt."""
    language: str
    repo_name: str
    date_str: str
    dimension: str
    source_file_count: int
    dimensions_data: dict
    standards_dir: Path | None = None
    manifest: "SourceManifest | None" = None
    target: "AnalysisTarget | None" = None
    extra_vars: dict[str, str] = field(default_factory=dict)
    work_dir: Path | None = None


_TEMPLATE_HASH_CACHE_SIZE = 128


@lru_cache(maxsize=_TEMPLATE_HASH_CACHE_SIZE)
def _template_hash(template: str) -> str:
    """Return a short hash of the template string, computed once per unique template."""
    return hashlib.sha256(template.encode()).hexdigest()[:12]


_TPL_DISCIPLINE = "DISCIPLINE"
_TPL_REPO_NAME = "REPO_NAME"
_TPL_DATE = "DATE"
_TPL_DIMENSION = "DIMENSION"
_TPL_SOURCE_FILE_COUNT = "SOURCE_FILE_COUNT"
_TPL_STANDARDS_CHECKLIST = "STANDARDS_CHECKLIST"
_TPL_ANALYSIS_GUIDANCE = "ANALYSIS_GUIDANCE"
_TPL_DIMENSIONS = "DIMENSIONS"
_TPL_PROMPT_HASH = "PROMPT_HASH"
_TPL_SOURCE_MANIFEST = "SOURCE_MANIFEST"
_TPL_DIMENSION_LIST = "DIMENSION_LIST"
_TPL_STANDARDS_CHECKLISTS = "STANDARDS_CHECKLISTS"


def _render_manifest_context(context: PromptContext) -> str:
    """Render the source manifest context for the prompt.

    When a target is set, renders target-specific context (with other-module info).
    Otherwise falls back to the whole-repo manifest context.
    """
    if context.target is not None and context.manifest is not None:
        other_targets = [t for t in context.manifest.targets if t.name != context.target.name]
        return context.target.to_prompt_context(
            repo_total_files=context.manifest.total_files,
            other_targets=other_targets or None,
        )
    if context.manifest is not None:
        return context.manifest.to_prompt_context()
    return _NO_GUIDANCE


_STANDARDS_FILE_PREFIX = ".quodeq_standards_"


def _write_standards_file(work_dir: Path, dimension: str, content: str) -> Path:
    """Write standards checklist to a file in the work directory.

    Returns the absolute path to the written file.
    """
    standards_path = work_dir / f"{_STANDARDS_FILE_PREFIX}{dimension}.md"
    try:
        standards_path.write_text(content)
    except OSError as exc:
        raise OSError(f"Failed to write standards file {standards_path}: {exc}") from exc
    return standards_path


def _standards_read_instruction(standards_path: Path) -> str:
    """Return prompt text instructing the AI to read the standards file."""
    return (
        f"**FIRST ACTION:** Read the standards checklist from `{standards_path}`\n"
        f"This file contains all requirements you must evaluate against. "
        f"Read it before analyzing any source files."
    )


def build_analysis_prompt(template: str, context: PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension)
    prompt_hash = _template_hash(template)

    standards_checklist = _NO_STANDARDS
    if context.standards_dir:
        compiled_dir = context.standards_dir / "compiled"
        if compiled_dir.exists():
            if context.work_dir:
                compact = render_compact_standards(compiled_dir, context.dimension)
                if compact not in (_NO_STANDARDS_FOR_DIM,):
                    standards_path = _write_standards_file(
                        context.work_dir, context.dimension, compact,
                    )
                    standards_checklist = _standards_read_instruction(standards_path)
                else:
                    standards_checklist = compact
            else:
                standards_checklist = render_compiled_standards(compiled_dir, context.dimension)

    manifest_context = _render_manifest_context(context)

    values = {
        _TPL_DISCIPLINE: context.language,
        _TPL_REPO_NAME: context.repo_name,
        _TPL_DATE: context.date_str,
        _TPL_DIMENSION: context.dimension,
        _TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        _TPL_STANDARDS_CHECKLIST: standards_checklist,
        _TPL_ANALYSIS_GUIDANCE: manifest_context,
        _TPL_DIMENSIONS: dimensions_text,
        _TPL_PROMPT_HASH: prompt_hash,
        _TPL_SOURCE_MANIFEST: manifest_context,
    }
    if context.extra_vars:
        values.update(context.extra_vars)
    return render_template(template, values)


def _render_all_standards(standards_dir: Path, dimensions: list[str]) -> str:
    """Render compact standards for all dimensions, separated by headers."""
    compiled_dir = standards_dir / "compiled"
    if not compiled_dir.exists():
        return _NO_STANDARDS
    sections = []
    for dim in dimensions:
        compact = render_compact_standards(compiled_dir, dim)
        if compact != _NO_STANDARDS_FOR_DIM:
            sections.append(f"## {dim.title()}\n\n{compact}")
    return "\n\n".join(sections) if sections else _NO_STANDARDS


def build_consolidated_prompt(
    dimensions: list[str],
    context: PromptContext,
    template: str | None = None,
) -> str:
    """Build a multi-dimension analysis prompt with all standards inline."""
    if template is None:
        template = load_template(template_name="consolidated.md")

    standards_text = _render_all_standards(
        context.standards_dir, dimensions,
    ) if context.standards_dir else _NO_STANDARDS

    manifest_context = _render_manifest_context(context)
    prompt_hash = _template_hash(template)

    values = {
        _TPL_DISCIPLINE: context.language,
        _TPL_REPO_NAME: context.repo_name,
        _TPL_DATE: context.date_str,
        _TPL_DIMENSION_LIST: ", ".join(dimensions),
        _TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
        _TPL_STANDARDS_CHECKLISTS: standards_text,
        _TPL_ANALYSIS_GUIDANCE: manifest_context,
        _TPL_PROMPT_HASH: prompt_hash,
        _TPL_SOURCE_MANIFEST: manifest_context,
    }
    if context.extra_vars:
        values.update(context.extra_vars)
    return render_template(template, values)
