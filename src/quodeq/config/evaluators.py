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
    discipline: str,
    dimension: str,
    practices_dir: Path,
    dimensions_dir: Path,
    output_path: Path,
    date_value: str,
) -> str:
    """Render an evaluator prompt by substituting context values into a template."""
    ctx = EvaluatorContext(
        discipline=discipline,
        dimension=dimension,
        practices_dir=practices_dir,
        dimensions_dir=dimensions_dir,
        output_path=output_path,
        date_value=date_value,
    )
    template = template_path.read_text()
    return render_template(
        template,
        {
            "DISCIPLINE": ctx.discipline,
            "DIMENSION": ctx.dimension,
            "PRACTICES_DIR": str(ctx.practices_dir),
            "DIMENSIONS_DIR": str(ctx.dimensions_dir),
            "OUTPUT": str(ctx.output_path),
            "DATE": ctx.date_value,
        },
    )
