"""Simple mustache-style template rendering for prompt files."""

from __future__ import annotations

import logging
import re

_logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` placeholders in a template string with the given values."""
    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in values:
            return values[key]
        return match.group(0)  # leave unmatched placeholders intact

    rendered = _PLACEHOLDER_RE.sub(_replace, template)

    remaining = _PLACEHOLDER_RE.findall(rendered)
    if remaining:
        _logger.warning(
            "Unreplaced template placeholders: %s",
            ", ".join(f"{{{{{p}}}}}" for p in remaining),
        )

    return rendered
