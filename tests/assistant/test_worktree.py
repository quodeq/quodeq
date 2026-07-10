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
