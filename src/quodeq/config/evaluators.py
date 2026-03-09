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
    context: EvaluatorContext | None = None,
    discipline: str = "",
    dimension: str = "",
    practices_dir: Path | None = None,
    dimensions_dir: Path | None = None,
    output_path: Path | None = None,
    date_value: str = "",
) -> str:
    """Render an evaluator prompt by substituting context values into a template.

    Accepts either a pre-built *context* or individual keyword arguments.
    """
    if context is None:
        context = EvaluatorContext(
            discipline=discipline,
            dimension=dimension,
            practices_dir=practices_dir or Path(),
            dimensions_dir=dimensions_dir or Path(),
            output_path=output_path or Path(),
            date_value=date_value,
        )
    template = template_path.read_text()
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
