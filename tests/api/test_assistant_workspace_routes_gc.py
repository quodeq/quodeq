"""Assistant worktree garbage collection against real session worktrees."""
from tests.api._assistant_workspace_fixtures import (  # noqa: F401 -- app/client/repo are pytest fixtures
    _session_with_worktree,
    app,
    client,
    repo,
)


def _branch_exists(repo, branch):
    from quodeq.assistant.worktree import run
    out = run(["git", "-C", str(repo), "branch", "--list", branch])
    return bool(out.strip())


def test_gc_removes_abandoned_active_worktree_and_branch(app, client, repo):
    # A write session the user never resolved leaks a worktree + quodeq/fix-*
    # branch in their real repo. GC with an elapsed TTL must remove both and
    # mark the row, not just flip status when the dir already vanished.
    from quodeq.assistant.worktree import gc_worktrees
    sid, store, manager = _session_with_worktree(app, client, repo)
    assert manager.path.exists()
    assert _branch_exists(repo, manager.branch)

    gc_worktrees(store, ttl_hours=0)  # ttl=0 => any active worktree is abandoned

    assert not manager.path.exists(), "abandoned worktree dir must be removed"
    assert not _branch_exists(repo, manager.branch), "fix branch must be deleted"
    assert store.get_worktree(sid)["status"] == "discarded"


def test_gc_keeps_recent_active_worktree(app, client, repo):
    from quodeq.assistant.worktree import gc_worktrees
    sid, store, manager = _session_with_worktree(app, client, repo)
    gc_worktrees(store, ttl_hours=72)  # created just now => under the TTL
    assert manager.path.exists()
    assert store.get_worktree(sid)["status"] == "active"


def test_gc_retries_a_failed_remove_on_a_terminal_row(app, client, repo):
    # apply/pr set the row terminal then remove(); if remove() failed the dir
    # lingers with a non-active row the old GC never revisited. GC must retry.
    from quodeq.assistant.worktree import gc_worktrees
    sid, store, manager = _session_with_worktree(app, client, repo)
    store.set_worktree_status(sid, "applied")  # terminal, but dir still exists
    assert manager.path.exists()

    gc_worktrees(store, ttl_hours=72)

    assert not manager.path.exists(), "leftover worktree of a terminal row must be removed"


def test_gc_marks_active_row_stale_when_dir_vanished(app, client, repo):
    from quodeq.assistant.worktree import gc_worktrees
    import shutil
    sid, store, manager = _session_with_worktree(app, client, repo)
    shutil.rmtree(manager.path)  # crash / external removal
    gc_worktrees(store, ttl_hours=72)
    assert store.get_worktree(sid)["status"] == "stale"
