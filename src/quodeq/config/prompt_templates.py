"""Simple mustache-style template rendering for prompt files."""

from __future__ import annotations


def render_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` placeholders in a template string with the given values."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered
