"""Tests for repo_clone: clone-destination naming and cleanup blast radius.

A trailing-slash URL used to produce an empty repo name, making the clone
destination the mkdtemp dir itself; cleanup_cloned_repo removes the
destination's *parent*, which in that case was the system temp root.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

from quodeq.data.fs.repo_clone import cleanup_cloned_repo, prepare_repository


class TestPrepareRepositoryDestination:
    def test_trailing_slash_url_clones_into_subdir_of_tempdir(self, monkeypatch):
        # Trailing slash passes validate_remote_url but yields an empty
        # basename; the clone dest must still be a subdir of the mkdtemp
        # dir so cleanup's parent-removal can never reach the temp root.
        monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")
        with patch("quodeq.data.fs.repo_clone.subprocess.run") as run:
            dest = Path(prepare_repository("https://github.com/user/repo/"))
        run.assert_called_once()
        temp_root = Path(tempfile.gettempdir()).resolve()
        assert dest.resolve().parent != temp_root, (
            "clone dest is directly inside the system temp root; "
            "cleanup_cloned_repo would rmtree the temp root itself"
        )


class TestCleanupClonedRepo:
    def test_never_removes_temp_root_when_dest_is_directly_inside(self, tmp_path, monkeypatch):
        # Disaster shape (pre-fix trailing-slash URLs): dest IS the mkdtemp
        # dir, so parent-removal would rmtree the whole system temp root.
        # Cleanup must remove only the clone and leave siblings untouched.
        monkeypatch.setattr(
            "quodeq.data.fs.repo_clone.tempfile.gettempdir", lambda: str(tmp_path)
        )
        clone = tmp_path / "clone"
        clone.mkdir()
        (clone / "file.py").write_text("x")
        sibling = tmp_path / "unrelated.txt"
        sibling.write_text("keep")

        cleanup_cloned_repo(str(clone))

        assert tmp_path.exists(), "system temp root was deleted"
        assert sibling.exists(), "sibling of the clone was deleted"
        assert not clone.exists(), "the clone itself should still be cleaned up"

    def test_removes_mkdtemp_parent_for_legacy_clone_dest(self, tmp_path, monkeypatch):
        # Normal legacy shape: dest = <mkdtemp>/<repo_name>. Cleanup removes
        # the whole mkdtemp dir, not just the clone inside it.
        monkeypatch.setattr(
            "quodeq.data.fs.repo_clone.tempfile.gettempdir", lambda: str(tmp_path)
        )
        mkdtemp_dir = tmp_path / "tmpabc123"
        dest = mkdtemp_dir / "repo"
        dest.mkdir(parents=True)

        cleanup_cloned_repo(str(dest))

        assert not mkdtemp_dir.exists()
        assert tmp_path.exists()

    def test_refuses_paths_outside_temp_root(self, tmp_path, monkeypatch):
        # A path outside the temp root (e.g. a local project dir passed by
        # mistake) must never be deleted, nor its parent.
        fake_temp = tmp_path / "temp"
        fake_temp.mkdir()
        monkeypatch.setattr(
            "quodeq.data.fs.repo_clone.tempfile.gettempdir", lambda: str(fake_temp)
        )
        project = tmp_path / "home" / "project"
        project.mkdir(parents=True)

        cleanup_cloned_repo(str(project))

        assert project.exists()
        assert (tmp_path / "home").exists()
