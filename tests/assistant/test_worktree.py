import pytest

from quodeq.assistant.worktree import (
    WorktreeError, WorktreeManager, _run, diff_stats, diff_text)


@pytest.fixture()
def repo(tmp_path):
    """A real git repo with one committed file."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(["git", "-C", str(root), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(root), "config", "user.name", "T"])
    _run(["git", "-C", str(root), "config", "user.email", "t@example.com"])
    (root / "app.py").write_bytes(b"print('hi')\n")
    _run(["git", "-C", str(root), "add", "-A"])
    _run(["git", "-C", str(root), "commit", "-q", "-m", "init"])
    return root


@pytest.fixture()
def manager(repo, tmp_path):
    m = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                    base=tmp_path / "wts")
    m.create()
    return m


def test_for_session_paths(repo, tmp_path):
    m = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                    base=tmp_path / "wts")
    assert m.branch == "quodeq/fix-abcdef12"
    assert m.path == tmp_path / "wts" / "proj" / "abcdef12"


def test_create_and_exists(manager):
    assert manager.exists()
    assert (manager.path / "app.py").read_bytes() == b"print('hi')\n"


def test_create_branch_collision_suffixes(repo, tmp_path):
    m1 = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                     base=tmp_path / "w1")
    m1.create()
    m2 = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                     base=tmp_path / "w2")
    m2.create()
    assert m2.branch == "quodeq/fix-abcdef12-2"


def test_diff_covers_edit_and_new_file(manager):
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    (manager.path / "new.py").write_bytes(b"x = 1\n")
    text = diff_text(manager.path)
    assert "-print('hi')" in text and "+print('bye')" in text
    assert "new.py" in text
    stats = diff_stats(manager.path)
    assert {s["file"] for s in stats} >= {"app.py", "new.py"}


def test_remove_deletes_worktree_and_branch(manager, repo):
    branch = manager.branch
    manager.remove()
    assert not manager.path.exists()
    out = _run(["git", "-C", str(repo), "branch", "--list", branch])
    assert out.strip() == ""


def test_run_raises_on_failure(repo):
    with pytest.raises(WorktreeError):
        _run(["git", "-C", str(repo), "not-a-command"])


def test_create_recovers_from_stale_dir(repo, tmp_path):
    m = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                    base=tmp_path / "wts")
    m.path.mkdir(parents=True)
    (m.path / ".DS_Store").write_bytes(b"junk")
    m.create()
    assert m.exists() and m.branch == "quodeq/fix-abcdef12"


def test_for_session_sanitizes_project_segment(repo, tmp_path):
    base = tmp_path / "wts"
    m = WorktreeManager.for_session(repo, "../evil/../../name", "abcdef1234567890",
                                    base=base)
    assert base.resolve() in m.path.resolve().parents


def test_remove_fallback_when_dir_deleted_out_of_band(manager, repo):
    import shutil as _shutil
    _shutil.rmtree(manager.path)
    manager.remove()  # must not raise; prunes and deletes the branch
    out = _run(["git", "-C", str(repo), "branch", "--list", manager.branch])
    assert out.strip() == ""


def test_apply_to_repo_leaves_uncommitted_changes(manager, repo):
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    stats = manager.apply_to_repo()
    assert (repo / "app.py").read_bytes() == b"print('bye')\n"
    assert stats and stats[0]["file"] == "app.py"
    # uncommitted: repo status is dirty
    out = _run(["git", "-C", str(repo), "status", "--porcelain"])
    assert "app.py" in out


def test_apply_conflict_applies_nothing(manager, repo):
    (manager.path / "app.py").write_bytes(b"print('worktree')\n")
    (repo / "app.py").write_bytes(b"print('diverged')\n")  # user edited too
    with pytest.raises(WorktreeError):
        manager.apply_to_repo()
    assert (repo / "app.py").read_bytes() == b"print('diverged')\n"


def test_apply_no_changes_errors(manager):
    with pytest.raises(WorktreeError, match="no changes"):
        manager.apply_to_repo()


def test_apply_binary_change(manager, repo):
    (manager.path / "logo.bin").write_bytes(b"\x00\x01\x02\xff")
    manager.apply_to_repo()
    assert (repo / "logo.bin").read_bytes() == b"\x00\x01\x02\xff"


def test_apply_propagates_deletion(manager, repo):
    (manager.path / "app.py").unlink()
    manager.apply_to_repo()
    assert not (repo / "app.py").exists()


def test_diff_text_shows_deletion(manager):
    (manager.path / "app.py").unlink()
    text = diff_text(manager.path)
    assert "-print('hi')" in text
    assert diff_stats(manager.path)[0]["file"] == "app.py"


def test_apply_leaves_no_patch_artifacts_in_worktree(manager, repo):
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    manager.apply_to_repo()
    assert not list(manager.path.glob("*.patch"))
    text = diff_text(manager.path)
    assert ".patch" not in text


def test_create_pr_fail_soft_without_gh(manager, monkeypatch):
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    monkeypatch.setattr("quodeq.assistant.worktree.shutil.which", lambda _: None)
    # no origin remote in the fixture repo: push fails first, branch is kept
    result = manager.create_pr("t", "b")
    assert result["prUrl"] is None
    assert result["branch"] == manager.branch
    assert "push failed" in result["message"].lower()


def test_create_pr_push_failure_restores_worktree_changes(manager, repo):
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    result = manager.create_pr("t", "b")           # fixture repo has no origin -> push fails
    assert result["pushed"] is False
    # changes are back in the working tree (not stranded in a commit)
    assert "print('bye')" in diff_text(manager.path)
    stats = manager.apply_to_repo()                 # in-app apply works again
    assert stats and (repo / "app.py").read_bytes() == b"print('bye')\n"


def test_commit_all_returns_committed(manager):
    assert manager.commit_all("m") is False          # clean worktree
    (manager.path / "app.py").write_bytes(b"print('bye')\n")
    assert manager.commit_all("m") is True


from quodeq.assistant.worktree import ensure_session_worktree, gc_stale_worktrees
from quodeq.data.sqlite.assistant_repository import AssistantRepository


def _store(tmp_path):
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama", project_id="proj")
    return store


def test_ensure_creates_once_then_reuses(repo, tmp_path):
    store = _store(tmp_path)
    m1 = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                 session_id="s1", base=tmp_path / "wts")
    assert m1.exists()
    assert store.get_worktree("s1")["branch"] == m1.branch
    m2 = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                 session_id="s1", base=tmp_path / "wts")
    assert m2.path == m1.path and m2.branch == m1.branch


def test_ensure_after_terminal_status_makes_fresh_worktree(repo, tmp_path):
    store = _store(tmp_path)
    m1 = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                 session_id="s1", base=tmp_path / "wts")
    m1.remove()
    store.set_worktree_status("s1", "discarded")
    m2 = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                 session_id="s1", base=tmp_path / "wts")
    assert m2.exists()
    assert store.get_worktree("s1")["status"] == "active"


def test_gc_marks_missing_paths_stale(repo, tmp_path):
    store = _store(tmp_path)
    store.upsert_worktree(session_id="s1", project_id="proj", repo_root=str(repo),
                          path=str(tmp_path / "gone"), branch="quodeq/fix-x")
    gc_stale_worktrees(store)
    assert store.get_worktree("s1")["status"] == "stale"
