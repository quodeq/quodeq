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
    from quodeq.analysis.manifest import SourceManifest

_logger = logging.getLogger(__name__)

_NO_GUIDANCE = "_No additional guidance._"
_NO_STANDARDS = "_No compiled standards available._"
_NO_STANDARDS_FOR_DIM = "_No compiled standards for this dimension._"
_STANDARDS_READ_ERROR = "_Could not read compiled standards._"


def render_compiled_standards(compiled_dir: Path, dimension: str) -> str:
    """Render compiled standards as a requirements checklist organized by principle."""
    compiled_file = compiled_dir / f"{dimension}.json"
    if not compiled_file.exists():
        return _NO_STANDARDS_FOR_DIM

    try:
        data = read_json(compiled_file)
    except (OSError, ValueError) as exc:
        _logger.warning("Could not read compiled standards %s: %s", compiled_file, exc)
        return _STANDARDS_READ_ERROR
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
    plugin_id: str
    repo_name: str
    date_str: str
    dimension: str
    source_file_count: int
    dimensions_data: dict
    analysis_md: str = ""
    standards_dir: Path | None = None
    manifest: "SourceManifest | None" = None


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


def _render_manifest_or_guidance(context: PromptContext) -> str:
    """Render either the source manifest context (universal) or analysis guidance (legacy)."""
    if context.manifest is not None:
        return context.manifest.to_prompt_context()
    return context.analysis_md or _NO_GUIDANCE


def build_analysis_prompt(template: str, context: PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension)
    prompt_hash = _template_hash(template)

    standards_checklist = _NO_STANDARDS
    if context.standards_dir:
        compiled_dir = context.standards_dir / "compiled"
        if compiled_dir.exists():
            standards_checklist = render_compiled_standards(compiled_dir, context.dimension)

    manifest_or_guidance = _render_manifest_or_guidance(context)

    return render_template(
        template,
        {
            _TPL_DISCIPLINE: context.plugin_id,
            _TPL_REPO_NAME: context.repo_name,
            _TPL_DATE: context.date_str,
            _TPL_DIMENSION: context.dimension,
            _TPL_SOURCE_FILE_COUNT: str(context.source_file_count),
            _TPL_STANDARDS_CHECKLIST: standards_checklist,
            _TPL_ANALYSIS_GUIDANCE: manifest_or_guidance,
            _TPL_DIMENSIONS: dimensions_text,
            _TPL_PROMPT_HASH: prompt_hash,
            _TPL_SOURCE_MANIFEST: manifest_or_guidance,
        },
    )
