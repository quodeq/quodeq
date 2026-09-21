"""Simple mustache-style template rendering for prompt files."""

from __future__ import annotations

import logging
import re

_logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, values: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` placeholders in *template* with *values*.

    A placeholder with no matching key is left in the output verbatim rather
    than blanked, so a missing value shows up in the rendered prompt instead
    of silently disappearing; those keys are also logged at warning level.
    Keys that appear only in substituted content are not re-expanded.
    """
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
