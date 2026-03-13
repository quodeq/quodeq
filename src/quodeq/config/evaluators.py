"""Evaluator prompt construction from templates and context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.config.prompt_templates import render_template


@dataclass(frozen=True)
class EvaluatorContext:
    """Groups the parameters needed to build an evaluator prompt."""
    discipline: str
    dimension: str
    practices_dir: Path
    dimensions_dir: Path
    output_path: Path
    date_value: str


def build_evaluator_prompt(
    *,
    template_path: Path,
    context: EvaluatorContext,
) -> str:
    """Render an evaluator prompt by substituting context values into a template."""
    try:
        template = template_path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot read template {template_path}: {exc}") from exc
    return render_template(
        template,
        {
            "DISCIPLINE": context.discipline,
            "DIMENSION": context.dimension,
            "PRACTICES_DIR": str(context.practices_dir),
            "DIMENSIONS_DIR": str(context.dimensions_dir),
            "OUTPUT": str(context.output_path),
            "DATE": context.date_value,
        },
    )
