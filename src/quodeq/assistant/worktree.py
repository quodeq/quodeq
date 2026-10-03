"""Git-worktree lifecycle for assistant fix sessions.

The low-level git primitives (``WorktreeError``, ``WorktreeStatus``,
``run_git``, ``run_git_bytes``, ``diff_text``, ``diff_stats``,
``worktrees_base``, ``worktree_ttl_hours``) live in ``_worktree_git.py``, a
true leaf module, and are re-exported here so existing
``quodeq.assistant.worktree.<name>`` imports and patches keep working.
``WorktreeManager``/``ensure_session_worktree`` (``_worktree_manager.py``)
and ``gc_stale_worktrees``/``gc_worktrees`` (``_worktree_gc.py``) import
their git/error primitives directly from ``_worktree_git.py``, not from this
module, so there is no cycle: this module is the only one that imports both
the leaf and its two consumers.
"""
from __future__ import annotations

# Not called directly in this module anymore (WorktreeManager.create_pr moved
# to _worktree_manager.py) -- kept imported so this module still exposes a
# `shutil` attribute: tests patch `quodeq.assistant.worktree.shutil.which`,
# which requires that dotted path to resolve.
import shutil  # noqa: F401 - patch target attribute holder

from quodeq.assistant._worktree_git import (  # noqa: F401 — re-export/patch target
    WorktreeError,
    WorktreeStatus,
    diff_stats,
    diff_text,
    run_git,
    run_git_bytes,
    worktree_ttl_hours,
    worktrees_base,
)
from quodeq.assistant._worktree_manager import (  # noqa: F401 — re-export
    PrResult, PrResultReason, WorktreeManager, ensure_session_worktree,
)
from quodeq.assistant._worktree_gc import (  # noqa: F401 — re-export
    gc_stale_worktrees, gc_worktrees,
)
