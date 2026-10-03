"""WorktreeStatus is the assistant ``worktrees`` table's status column
vocabulary.

The CHECK-equality test lives in tests/data/sqlite/test_assistant_schema.py,
which already imports the private ASSISTANT_DDL string (the private-imports
gate's ceiling only shrinks, so this test doesn't add a second import site)."""
from __future__ import annotations

from quodeq.assistant.worktree import WorktreeStatus


def test_worktree_status_members():
    assert {s.value for s in WorktreeStatus} == {
        "active", "applied", "pr_created", "discarded", "stale",
    }
