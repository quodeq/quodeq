"""Simple mustache-style template rendering for prompt files."""

from __future__ import annotations

import logging
import re

_logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` placeholders in a template string with the given values."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)

    remaining = _PLACEHOLDER_RE.findall(rendered)
    if remaining:
        _logger.warning(
            "Unreplaced template placeholders: %s",
            ", ".join(f"{{{{{p}}}}}" for p in remaining),
        )

    return rendered
