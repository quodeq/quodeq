"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from quodeq.config.prompt_templates import render_template


def render_compiled_standards(compiled_dir: Path, dimension: str) -> str:
    """Render compiled standards as a compact CWE checklist organized by principle."""
    compiled_file = compiled_dir / f"{dimension}.json"
    if not compiled_file.exists():
        return "_No compiled standards for this dimension._"

    data = json.loads(compiled_file.read_text())
    lines = []
    for principle in data.get("principles", []):
        cwes = principle.get("cwes", [])
        if not cwes:
            continue
        lines.append(f"### {principle['name']} ({len(cwes)} CWEs)")
        for cwe in cwes:
            lines.append(f"- CWE-{cwe['id']}: {cwe['name']}")
        lines.append("")
    return "\n".join(lines)


def _load_iso_requirements(standards_dir: Path, dimension: str) -> list[str]:
    """Load ISO 25010 sub-characteristic requirements for a dimension.

    Returns a list of formatted lines, or an empty list if the file is absent or invalid.
    """
    std_file = standards_dir / "iso25010" / f"{dimension}.json"
    if not std_file.exists():
        return []
    try:
        std = json.loads(std_file.read_text())
        sub_chars = std.get("sub_characteristics", [])
        if not sub_chars or not isinstance(sub_chars[0], dict):
            return []
        lines = ["\n**Requirements:**"]
        for sc in sub_chars:
            lines.append(f"\n#### {sc['name']}")
            for req in sc.get("requirements", []):
                lines.append(f"- **{req['id']}**: {req['text']}")
        return lines
    except (json.JSONDecodeError, KeyError):
        return []


def render_dimensions(dimensions_data: dict, dimension: str, standards_dir: Path | None = None) -> str:
    """Format dimension info with ISO 25010 requirements for prompt inclusion."""
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

    if standards_dir and iso:
        lines.extend(_load_iso_requirements(standards_dir, dimension))

    return "\n".join(lines)


def load_template(template_path: Path | None = None, *, prompts_dir: Path | None = None) -> str:
    """Load the compass.md prompt template.

    Args:
        template_path: Explicit path to a template file (takes priority).
        prompts_dir: Directory containing prompt templates; used to locate
            ``compass.md`` when *template_path* is not given.
    """
    if template_path:
        return template_path.read_text()
    if prompts_dir is None:
        from quodeq.config.paths import default_paths
        prompts_dir = default_paths().prompts_dir
    return (prompts_dir / "compass.md").read_text()


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


def build_analysis_prompt(template: str, context: PromptContext) -> str:
    """Build a complete per-dimension analysis prompt from the template."""
    dimensions_text = render_dimensions(context.dimensions_data, context.dimension, context.standards_dir)
    prompt_hash = hashlib.sha256(template.encode()).hexdigest()[:12]

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
