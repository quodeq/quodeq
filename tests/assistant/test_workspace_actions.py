"""workspace_actions: turn claim, status gates and release on every path."""
from __future__ import annotations

import pytest

from quodeq.assistant import workspace_actions as wa
from quodeq.assistant.worktree import WorktreeError


class _Store:
    def __init__(self, row):
        self.row = row
        self.statuses: list[str] = []

    def get_worktree(self, sid):
        return self.row

    def set_worktree_status(self, sid, status):
        self.statuses.append(status)


class _Turns:
    def __init__(self, free=True):
        self.free = free
        self.released: list[str] = []

    def claim(self, sid):
        return self.free

    def release(self, sid):
        self.released.append(sid)


def _row(status):
    return {"status": status, "repo_root": "/r", "path": "/r/wt", "branch": "b"}


class _Manager:
    def __init__(self, fail=False):
        self.fail = fail
        self.removed = 0

    def apply_to_repo(self):
        if self.fail:
            raise WorktreeError("boom")
        return [{"file": "a"}]

    def remove(self, **_kwargs):
        self.removed += 1


@pytest.fixture
def manager(monkeypatch):
    # Patch the public class the module builds, not its private _manager
    # helper: the tests private-import ratchet may not grow.
    m = _Manager()
    monkeypatch.setattr("quodeq.assistant.workspace_actions.WorktreeManager", lambda **_kw: m)
    return m


def _call(fn, store, turns):
    return fn(store, "s1", claim_turn=turns.claim, release_turn=turns.release)


def test_busy_turn_is_refused_and_nothing_released():
    turns = _Turns(free=False)
    assert _call(wa.apply_workspace, _Store(_row("active")), turns).kind == "turn_busy"
    assert turns.released == []


@pytest.mark.parametrize("status", ["stale", "applied"])
def test_apply_refuses_non_active_with_status_detail(status):
    turns = _Turns()
    out = _call(wa.apply_workspace, _Store(_row(status)), turns)
    assert (out.kind, out.detail) == ("not_active", status)
    assert turns.released == ["s1"]


def test_apply_on_missing_row_is_not_active_gone():
    out = _call(wa.apply_workspace, _Store(None), _Turns())
    assert (out.kind, out.detail) == ("not_active", "gone")


def test_discard_on_missing_row_is_gone():
    assert _call(wa.discard_workspace, _Store(None), _Turns()).kind == "gone"


def test_discard_allows_stale(manager):
    store = _Store(_row("stale"))
    assert _call(wa.discard_workspace, store, _Turns()).kind == "discarded"
    assert store.statuses == ["discarded"]
    assert manager.removed == 1


def test_apply_failure_releases_and_keeps_status(manager):
    manager.fail = True
    store, turns = _Store(_row("active")), _Turns()
    out = _call(wa.apply_workspace, store, turns)
    assert (out.kind, out.detail) == ("failed", "boom")
    assert store.statuses == []
    assert turns.released == ["s1"]


def test_release_runs_when_the_store_raises():
    class _Broken(_Store):
        def get_worktree(self, sid):
            raise RuntimeError("db gone")

    turns = _Turns()
    with pytest.raises(RuntimeError):
        _call(wa.apply_workspace, _Broken(None), turns)
    assert turns.released == ["s1"]


class TestManagerFactorySeam:
    """manager_factory injection: apply/create_pr/discard must use an
    injected factory, proving the module's WorktreeManager was never built."""

    def test_apply_uses_the_injected_manager_factory(self):
        fake = _Manager()
        seen_rows = []

        def factory(row):
            seen_rows.append(row)
            return fake

        store, turns = _Store(_row("active")), _Turns()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "quodeq.assistant.workspace_actions.WorktreeManager",
                lambda **_kw: (_ for _ in ()).throw(AssertionError("must not build WorktreeManager")),
            )
            out = wa.apply_workspace(
                store, "s1", claim_turn=turns.claim, release_turn=turns.release,
                manager_factory=factory,
            )

        assert out.kind == "applied"
        assert seen_rows == [_row("active")]

    def test_discard_uses_the_injected_manager_factory(self):
        fake = _Manager()
        store, turns = _Store(_row("stale")), _Turns()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "quodeq.assistant.workspace_actions.WorktreeManager",
                lambda **_kw: (_ for _ in ()).throw(AssertionError("must not build WorktreeManager")),
            )
            out = wa.discard_workspace(
                store, "s1", claim_turn=turns.claim, release_turn=turns.release,
                manager_factory=lambda row: fake,
            )

        assert out.kind == "discarded"
        assert fake.removed == 1

    def test_default_manager_factory_still_resolves_to_the_patched_worktreemanager(self, manager):
        """No manager_factory injected -> falls back to _manager(), which
        still resolves the module's patched WorktreeManager at call time
        (this is what the `manager` fixture patches)."""
        store, turns = _Store(_row("active")), _Turns()
        out = wa.apply_workspace(store, "s1", claim_turn=turns.claim, release_turn=turns.release)
        assert out.kind == "applied"
        assert manager.removed == 1
