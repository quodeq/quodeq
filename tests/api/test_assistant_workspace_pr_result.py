"""Assistant workspace PR route: exact-equality wire body per PrOutcome.

Characterizes ``_workspace_pr``'s whole JSON response (all 4
``WorktreeManager.create_pr`` outcomes), so the message text stays
byte-identical across the PrResult/PrOutcome route-shaping refactor.
"""
import sys

from tests.api._assistant_workspace_fixtures import (  # noqa: F401 -- app/client/repo are pytest fixtures
    _session_with_worktree,
    app,
    client,
    repo,
)


def _patch_push(monkeypatch, *, fail_with: str | None = None):
    """Push succeeds (returns "") unless *fail_with* is given, in which case
    the push step alone raises WorktreeError(fail_with); every other
    ``_git_worktree`` call (status/add/commit/reset) runs for real."""
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    orig = WorktreeManager._git_worktree

    def fake(self, *args):
        if args and args[0] == "push":
            if fail_with is not None:
                raise WorktreeError(fail_with)
            return ""
        return orig(self, *args)
    monkeypatch.setattr(WorktreeManager, "_git_worktree", fake)


def test_pr_push_fail_exact_body(app, client, repo, monkeypatch):
    sid, store, manager = _session_with_worktree(app, client, repo)
    _patch_push(monkeypatch, fail_with="no configured push destination")
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "prUrl": None, "branch": manager.branch, "pushed": False,
        "message": ("Push failed: no configured push destination. The changes are"
                   " back in the worktree; apply them or open a PR manually."),
    }
    assert store.get_worktree(sid)["status"] == "active"


def test_pr_no_gh_exact_body(app, client, repo, monkeypatch):
    sid, store, manager = _session_with_worktree(app, client, repo)
    _patch_push(monkeypatch)
    monkeypatch.setattr("quodeq.assistant.worktree.shutil.which", lambda _: None)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "prUrl": None, "branch": manager.branch, "pushed": True,
        "message": ("Branch pushed. Install and authenticate the gh"
                   " CLI, or open the PR from your git host."),
    }
    assert store.get_worktree(sid)["status"] == "active"


def test_pr_gh_fail_exact_body(app, client, repo, monkeypatch):
    from quodeq.assistant.worktree import WorktreeError
    sid, store, manager = _session_with_worktree(app, client, repo)
    _patch_push(monkeypatch)
    monkeypatch.setattr("quodeq.assistant.worktree.shutil.which", lambda _: "/usr/bin/gh")
    orig_run_git = sys.modules["quodeq.assistant._worktree_manager"].run_git

    def fake_run_git(argv, **kwargs):
        if argv[0] == "gh":
            raise WorktreeError("gh: not authenticated")
        return orig_run_git(argv, **kwargs)
    monkeypatch.setattr("quodeq.assistant._worktree_manager.run_git", fake_run_git)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "prUrl": None, "branch": manager.branch, "pushed": True,
        "message": "gh pr create failed: gh: not authenticated",
    }
    assert store.get_worktree(sid)["status"] == "active"


def test_pr_success_exact_body(app, client, repo, monkeypatch):
    sid, store, manager = _session_with_worktree(app, client, repo)
    _patch_push(monkeypatch)
    monkeypatch.setattr("quodeq.assistant.worktree.shutil.which", lambda _: "/usr/bin/gh")
    orig_run_git = sys.modules["quodeq.assistant._worktree_manager"].run_git

    def fake_run_git(argv, **kwargs):
        if argv[0] == "gh":
            return "https://github.com/example/repo/pull/42\n"
        return orig_run_git(argv, **kwargs)
    monkeypatch.setattr("quodeq.assistant._worktree_manager.run_git", fake_run_git)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    assert resp.status_code == 200
    assert resp.get_json() == {
        "prUrl": "https://github.com/example/repo/pull/42", "branch": manager.branch,
        "pushed": True, "message": "PR created",
    }
    assert store.get_worktree(sid)["status"] == "pr_created"
