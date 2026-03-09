from pathlib import Path

from quodeq.config.evaluators import build_evaluator_prompt


def test_build_evaluator_prompt_replaces_tokens(tmp_path):
    template = "Dimension={{DIMENSION}} Disc={{DISCIPLINE}} Date={{DATE}}"
    template_path = tmp_path / "dimension-mapper.md"
    template_path.write_text(template)
    prompt = build_evaluator_prompt(
        template_path=template_path,
        discipline="backend",
        dimension="maintainability",
        practices_dir=Path("/p"),
        dimensions_dir=Path("/d"),
        output_path=Path("/o.json"),
        date_value="2026-02-25",
    )
    assert "Disc=backend" in prompt
