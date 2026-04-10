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

    # Check only the template keys (not substituted content) for missing values
    template_keys = set(_PLACEHOLDER_RE.findall(template))
    missing = template_keys - set(values.keys())
    if missing:
        _logger.warning("Unresolved template placeholders: %s", ", ".join(sorted(missing)))

    return rendered
