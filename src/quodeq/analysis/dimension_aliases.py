"""Short aliases for dimension names used in CLI flags."""
from __future__ import annotations

DIMENSION_ALIASES: dict[str, str] = {
    "sec": "security",
    "rel": "reliability",
    "mnt": "maintainability",
    "perf": "performance",
    "flex": "flexibility",
    "ux": "usability",
}


def expand_dimension_aliases(value: str | None) -> str | None:
    """Expand short dimension aliases to full names in a comma-separated string.

    Accepts:
      - None → returns None
      - "" → returns ""
      - "sec,rel" → "security,reliability"
      - "security,rel" → "security,reliability" (mixing is fine)
      - "security" → "security" (unknown tokens passed through, validation happens downstream)

    Whitespace around items is stripped. Unknown tokens pass through unchanged so existing
    full names keep working and invalid names are caught by the existing validator.
    """
    if value is None:
        return None
    if not value:
        return ""
    tokens = [t.strip() for t in value.split(",")]
    expanded = [DIMENSION_ALIASES.get(t, t) for t in tokens]
    return ",".join(expanded)
