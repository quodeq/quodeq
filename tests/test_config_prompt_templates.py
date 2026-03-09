from quodeq.config.prompt_templates import render_template


def test_render_template_replaces_tokens():
    template = "Disc={{DISCIPLINE}} Date={{DATE}}"
    result = render_template(template, {"DISCIPLINE": "backend", "DATE": "2026-02-25"})
    assert result == "Disc=backend Date=2026-02-25"
