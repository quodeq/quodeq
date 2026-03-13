"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from quodeq.config.prompt_templates import render_template

_logger = logging.getLogger(__name__)


def render_compiled_standards(compiled_dir: Path, dimension: str) -> str:
    """Render compiled standards as a requirements checklist organized by principle."""
    compiled_file = compiled_dir / f"{dimension}.json"
    if not compiled_file.exists():
        return "_No compiled standards for this dimension._"

    try:
        data = json.loads(compiled_file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning("Could not read compiled standards %s: %s", compiled_file, exc)
        return "_Could not read compiled standards._"
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
        from quodeq.config.paths import default_paths
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


@lru_cache(maxsize=128)
def _template_hash(template: str) -> str:
    """Return a short hash of the template string, computed once per unique template."""
    return hashlib.sha256(template.encode()).hexdigest()[:12]


def build_analysis_prompt(template: str, context: PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension)
    prompt_hash = _template_hash(template)

    standards_checklist = "_No compiled standards available._"
    if context.standards_dir:
        compiled_dir = context.standards_dir / "compiled"
        if compiled_dir.exists():
            standards_checklist = render_compiled_standards(compiled_dir, context.dimension)

    return render_template(
        template,
        {
            "DISCIPLINE": context.plugin_id,
            "REPO_NAME": context.repo_name,
            "DATE": context.date_str,
            "DIMENSION": context.dimension,
            "SOURCE_FILE_COUNT": str(context.source_file_count),
            "STANDARDS_CHECKLIST": standards_checklist,
            "ANALYSIS_GUIDANCE": context.analysis_md or "_No additional guidance._",
            "DIMENSIONS": dimensions_text,
            "PROMPT_HASH": prompt_hash,
        },
    )
