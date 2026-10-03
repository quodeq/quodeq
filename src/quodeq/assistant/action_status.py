"""Lifecycle of a drafted assistant action.

data/sqlite/_assistant_schema.py's ``actions.status`` CHECK constraint
mirrors these values (SQL text can't reference this name, so the two are
kept equal by tests/assistant/test_action_status.py instead).
"""
from __future__ import annotations

from enum import StrEnum


class ActionStatus(StrEnum):
    """A drafted action moves drafted -> applied or drafted -> rejected, both
    claimed atomically (see apply_action.py)."""

    DRAFTED = "drafted"
    APPLIED = "applied"
    REJECTED = "rejected"
