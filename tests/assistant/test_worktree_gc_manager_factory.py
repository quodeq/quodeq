"""gc_worktrees manager_factory seam: an injected factory must build the
manager gc_worktrees drives, proving the real WorktreeManager was never
constructed."""
from __future__ import annotations

from quodeq.assistant.worktree import WorktreeStatus, gc_worktrees


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows
        self.statuses: list[tuple[str, str]] = []

    def list_all_worktrees(self):
        return self._rows

    def set_worktree_status(self, sid, status):
        self.statuses.append((sid, status))


def _row(status, path):
    return {
        "session_id": "s1", "status": status, "repo_root": "/r",
        "path": path, "branch": "b", "created_at": "2020-01-01 00:00:00",
    }


def test_gc_uses_the_injected_manager_factory(tmp_path):
    leftover = tmp_path / "leftover"
    leftover.mkdir()
    seen_rows = []

    class _FakeManager:
        def remove(self):
            pass

    def factory(row):
        seen_rows.append(row)
        return _FakeManager()

    row = _row(WorktreeStatus.ACTIVE, str(leftover))
    repo = _FakeRepo([row])

    gc_worktrees(repo, ttl_hours=0, manager_factory=factory)

    assert seen_rows == [row]
    assert repo.statuses == [("s1", WorktreeStatus.DISCARDED)]


def test_default_manager_factory_still_resolves_to_the_patched_worktreemanager(tmp_path, monkeypatch):
    """Existing behavior preserved: no manager_factory injected -> falls back
    to the module's WorktreeManager, resolved at call time (patchable)."""
    leftover = tmp_path / "leftover"
    leftover.mkdir()
    calls = []

    def fake_manager(**kwargs):
        calls.append(kwargs)

        class _M:
            def remove(self):
                pass
        return _M()

    monkeypatch.setattr("quodeq.assistant._worktree_gc.WorktreeManager", fake_manager)

    row = _row(WorktreeStatus.ACTIVE, str(leftover))
    repo = _FakeRepo([row])

    gc_worktrees(repo, ttl_hours=0)

    assert len(calls) == 1
    assert calls[0]["branch"] == "b"
