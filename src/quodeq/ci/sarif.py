"""Build a SARIF 2.1.0 document from Quodeq evaluation reports.

Pure: report dicts in, a SARIF dict out. No I/O. The CLI glue
(`export_cli.py`, `_cli_evaluation.py`) handles loading and writing.
"""
from __future__ import annotations

import re

from quodeq.context.precedent import fingerprint

# quodeq severity -> (SARIF result level, GitHub security-severity string).
# GitHub buckets security-severity: >=9.0 Critical, 7.0-8.9 High,
# 4.0-6.9 Medium, 0.1-3.9 Low. `level` is the separate SARIF axis.
_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    "critical": ("error", "9.0"),
    "major": ("error", "7.0"),
    "high": ("error", "7.0"),
    "minor": ("warning", "4.0"),
}
_DEFAULT_LEVEL_SEVERITY = ("note", "2.0")  # unknown/low/blank

# Ranking used for --min-severity filtering and worst-of rollup.
# Unknown/low/garbage all fall to the default (1).
_RANK = {"critical": 4, "major": 3, "high": 3, "minor": 2}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _severity_level(severity: str | None) -> str:
    return _SEVERITY_MAP.get((severity or "").lower(), _DEFAULT_LEVEL_SEVERITY)[0]


def _security_severity(severity: str | None) -> str:
    return _SEVERITY_MAP.get((severity or "").lower(), _DEFAULT_LEVEL_SEVERITY)[1]


def _severity_rank(severity: str | None) -> int:
    """Higher = more severe. Unknown/blank/garbage all rank lowest (1)."""
    return _RANK.get((severity or "").lower(), 1)


def _slug(text: str | None) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


def _rule_id(dimension: str | None, principle: str | None) -> str:
    return f"{(dimension or 'unknown').lower()}/{_slug(principle) or 'unknown'}"
