"""Prompt builder — assembles per-dimension analysis prompts from compass.md template."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def _sub(template: str, **kwargs: str) -> str:
    """Replace {{KEY}} placeholders in a template string."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


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

    # Load ISO 25010 standards if available
    if standards_dir and iso:
        std_file = standards_dir / "iso25010" / f"{dimension}.json"
        if std_file.exists():
            try:
                std = json.loads(std_file.read_text())
                sub_chars = std.get("sub_characteristics", [])
                if sub_chars and isinstance(sub_chars[0], dict):
                    lines.append("\n**Requirements:**")
                    for sc in sub_chars:
                        lines.append(f"\n#### {sc['name']}")
                        for req in sc.get("requirements", []):
                            lines.append(f"- **{req['id']}**: {req['text']}")
            except (json.JSONDecodeError, KeyError):
                pass

    return "\n".join(lines)


def load_template(template_path: Path | None = None) -> str:
    """Load the compass.md prompt template."""
    path = template_path or (_PROMPTS_DIR / "compass.md")
    return path.read_text()


def build_analysis_prompt(
    template: str,
    *,
    plugin_id: str,
    repo_name: str,
    date_str: str,
    dimension: str,
    source_file_count: int,
    dimensions_data: dict,
    analysis_md: str = "",
    standards_dir: Path | None = None,
) -> str:
    """Build a complete per-dimension analysis prompt from the template.

    Args:
        template: Raw compass.md template text.
        plugin_id: Plugin identifier (e.g. "typescript").
        repo_name: Repository name.
        date_str: Evaluation date string.
        dimension: The dimension being evaluated (e.g. "security").
        source_file_count: Total source files in the repo.
        dimensions_data: Parsed dimensions.json dict.
        analysis_md: Plugin-specific analysis guidance text.
        standards_dir: Path to standards/ directory.

    Returns:
        Fully rendered prompt string.
    """
    dimensions_text = render_dimensions(dimensions_data, dimension, standards_dir)
    prompt_hash = hashlib.sha256(template.encode()).hexdigest()[:12]

    standards_checklist = "_No compiled standards available._"
    if standards_dir:
        compiled_dir = standards_dir / "compiled"
        if compiled_dir.exists():
            standards_checklist = render_compiled_standards(compiled_dir, dimension)

    return _sub(
        template,
        DISCIPLINE=plugin_id,
        REPO_NAME=repo_name,
        DATE=date_str,
        DIMENSION=dimension,
        SOURCE_FILE_COUNT=str(source_file_count),
        STANDARDS_CHECKLIST=standards_checklist,
        ANALYSIS_GUIDANCE=analysis_md or "_No additional guidance._",
        DIMENSIONS=dimensions_text,
        PROMPT_HASH=prompt_hash,
    )
