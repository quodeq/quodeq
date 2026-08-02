"""Read the project's pattern-level suppression rules.

Stored next to the other per-project suppression state as
``<project_dir>/suppression_rules.json``:

    {"version": 1, "rules": [{"req": ..., "file": ..., "reason": ...}]}

Best-effort like its siblings: an absent, unreadable or malformed file yields
no rules. Individual entries are validated and skipped rather than raising —
one half-written rule must never suppress everything, and a suppression store
that fails closed is safer than one that fails open.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.types.suppression_rule import SuppressionRule

_FILENAME = "suppression_rules.json"
_logger = logging.getLogger(__name__)


def load_suppression_rules(project_dir: Path) -> tuple[SuppressionRule, ...]:
    """Return the project's suppression rules, or ``()`` when there are none."""
    path = project_dir / _FILENAME
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Ignoring malformed suppression rules %s: %s", path, exc)
        return ()
    raw_rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(raw_rules, list):
        return ()
    rules: list[SuppressionRule] = []
    for entry in raw_rules:
        if not isinstance(entry, dict):
            continue
        req, file, reason = entry.get("req"), entry.get("file"), entry.get("reason")
        # Every field is required: a rule missing its pattern would match far
        # more than intended, and one missing its reason is undocumented policy.
        if not (isinstance(req, str) and req and isinstance(file, str) and file
                and isinstance(reason, str) and reason):
            _logger.warning("Skipping incomplete suppression rule in %s: %r", path, entry)
            continue
        rules.append(SuppressionRule(req=req, file=file, reason=reason))
    return tuple(rules)
