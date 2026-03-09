from __future__ import annotations

from pathlib import Path

from quodeq.config.prompt_templates import render_template


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
    template = template_path.read_text()
    return render_template(
        template,
        {
            "DISCIPLINE": discipline,
            "DIMENSION": dimension,
            "PRACTICES_DIR": str(practices_dir),
            "DIMENSIONS_DIR": str(dimensions_dir),
            "OUTPUT": str(output_path),
            "DATE": date_value,
        },
    )
