"""Pattern-level suppression rule — an ADR expressed as data.

Dismissals are keyed ``(req, file, line)``, so a refactor that shifts a line
re-surfaces a finding the team already decided is acceptable. A rule matches
by requirement + file glob instead, letting one decision cover a pattern
("services importing quodeq.data.* is accepted per WS1") for as long as the
decision holds, wherever the code moves.

Rules are deliberately dumb: two globs and a mandatory human reason. Anything
smarter (severity ranges, expiry dates) should be argued for on its own.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SuppressionRule:
    """One accepted pattern. All three fields are required."""

    req: str
    """Requirement ID or glob (e.g. ``CLEA-DEP-01``, ``CLEA-DEP-*``, ``*``)."""

    file: str
    """Repo-relative path glob (``**`` spans directories)."""

    reason: str
    """Why this pattern is accepted. Required: an unexplained rule is a bug."""
