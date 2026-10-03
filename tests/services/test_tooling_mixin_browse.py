"""Tests for _browse_mixin.py: browse-path validation, directory/file listing and browse_repo."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.services.tooling_mixin import FsToolingMixin
from quodeq.shared.log_sink import SHARED_LOG


# ---------------------------------------------------------------------------
# _validate_browse_path
# ---------------------------------------------------------------------------


class TestValidateBrowsePath:
    def test_none_defaults_to_home(self):
        target, err = FsToolingMixin._validate_browse_path(None)
        assert target == Path.home()
        assert err is None

    def test_nonexistent_path(self):
        nonexistent = Path.home() / "___nonexistent_quodeq_test___"
        target, err = FsToolingMixin._validate_browse_path(str(nonexistent))
        assert err is not None
        assert err["error_code"] == "PATH_NOT_FOUND"

    def test_file_not_directory(self, tmp_path: Path):
        # Create file under HOME so it passes the boundary check
        import tempfile
        with tempfile.NamedTemporaryFile(dir=Path.home(), suffix=".txt", delete=False) as f:
            f.write(b"hello")
            fpath = f.name
        try:
            target, err = FsToolingMixin._validate_browse_path(fpath)
            assert err is not None
            assert err["error_code"] == "PATH_NOT_DIRECTORY"
        finally:
            Path(fpath).unlink(missing_ok=True)

    def test_outside_home(self, tmp_path: Path, monkeypatch):
        # Pin HOME to tmp_path so the root dir is deterministically outside
        # it, regardless of where the platform's real temp dir happens to
        # live relative to the real $HOME.
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        target, err = FsToolingMixin._validate_browse_path("/")
        assert err is not None
        assert err["error_code"] == "PATH_OUTSIDE_BOUNDARY"

    def test_valid_directory(self):
        target, err = FsToolingMixin._validate_browse_path(str(Path.home()))
        assert err is None


# ---------------------------------------------------------------------------
# _list_directories / _list_files
# ---------------------------------------------------------------------------


class TestListDirectories:
    def test_lists_non_hidden_dirs(self, tmp_path: Path):
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "file.txt").write_text("x")
        dirs = FsToolingMixin._list_directories(tmp_path)
        names = [d["name"] for d in dirs]
        assert "visible" in names
        assert ".hidden" not in names
        assert "file.txt" not in names

    def test_git_repo_detected(self, tmp_path: Path):
        repo = tmp_path / "myrepo"
        repo.mkdir()
        (repo / ".git").mkdir()
        dirs = FsToolingMixin._list_directories(tmp_path)
        myrepo = [d for d in dirs if d["name"] == "myrepo"][0]
        assert myrepo["isGitRepo"] is True

    def test_sorted_by_name(self, tmp_path: Path):
        for name in ["zebra", "alpha", "middle"]:
            (tmp_path / name).mkdir()
        dirs = FsToolingMixin._list_directories(tmp_path)
        names = [d["name"] for d in dirs]
        assert names == sorted(names)


class TestListFiles:
    def test_lists_non_hidden_files(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("x")
        (tmp_path / ".env").write_text("SECRET")
        (tmp_path / "subdir").mkdir()
        files = FsToolingMixin._list_files(tmp_path)
        names = [f["name"] for f in files]
        assert "readme.md" in names
        assert ".env" not in names
        assert "subdir" not in names

    def test_sorted_by_name(self, tmp_path: Path):
        for name in ["z.py", "a.py", "m.py"]:
            (tmp_path / name).write_text("pass")
        files = FsToolingMixin._list_files(tmp_path)
        names = [f["name"] for f in files]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# _build_browse_response
# ---------------------------------------------------------------------------


class TestBuildBrowseResponse:
    def test_basic_response(self, tmp_path: Path):
        dirs = [{"name": "a", "path": str(tmp_path / "a"), "isGitRepo": False}]
        resp = FsToolingMixin._build_browse_response(tmp_path, dirs)
        assert resp["current"] == str(tmp_path)
        assert resp["truncated"] is False
        assert "directories" in resp
        assert "files" not in resp

    def test_includes_files_when_provided(self, tmp_path: Path):
        files = [{"name": "f.py", "path": str(tmp_path / "f.py")}]
        resp = FsToolingMixin._build_browse_response(tmp_path, [], files)
        assert resp["files"] == files

    def test_truncated_flag(self, tmp_path: Path):
        dirs = [{"name": f"d{i}", "path": f"/d{i}", "isGitRepo": False} for i in range(600)]
        resp = FsToolingMixin._build_browse_response(tmp_path, dirs)
        assert resp["truncated"] is True
        assert len(resp["directories"]) == 500

    def test_parent_is_none_at_root(self):
        root = Path("/")
        resp = FsToolingMixin._build_browse_response(root, [])
        assert resp["parent"] is None


# ---------------------------------------------------------------------------
# browse_repo
# ---------------------------------------------------------------------------


class TestBrowseRepo:
    def test_returns_error_for_bad_path(self, tmp_path: Path):
        mixin = FsToolingMixin()
        result = mixin.browse_repo(str(tmp_path / "nonexistent"))
        assert "error" in result

    def test_returns_directories(self):
        mixin = FsToolingMixin()
        result = mixin.browse_repo(str(Path.home()))
        assert "directories" in result
        assert "current" in result

    def test_include_files(self):
        mixin = FsToolingMixin()
        result = mixin.browse_repo(str(Path.home()), include_files=True)
        assert "files" in result


@pytest.fixture
def browse_tree(tmp_path: Path, monkeypatch) -> Path:
    """A sample tree inside a redirected home.

    ``_validate_browse_path`` jails browsing to ``Path.home()``, which resolves
    ``$HOME`` at call time, so pointing HOME at tmp_path keeps the fixture out
    of the developer's real home directory.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() reads USERPROFILE on Windows and HOME elsewhere.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert Path.home() == tmp_path, "browse jail no longer follows the home env"
    base = tmp_path / "workspace"
    base.mkdir()
    (base / "beta").mkdir()
    (base / "alpha").mkdir()
    (base / "alpha" / ".git").mkdir()
    (base / ".hidden_dir").mkdir()
    (base / "z.py").write_text("pass")
    (base / "a.py").write_text("pass")
    (base / ".env").write_text("SECRET")
    return base


class TestBrowseRepoUsesTheListingHelpers:
    """browse_repo must not keep its own copy of the listing rules: it feeds
    one directory read to _list_directories/_list_files."""

    def test_matches_the_helpers_exactly(self, browse_tree: Path):
        result = FsToolingMixin().browse_repo(str(browse_tree), include_files=True)

        assert result["directories"] == FsToolingMixin._list_directories(browse_tree)
        assert result["files"] == FsToolingMixin._list_files(browse_tree)
        assert [d["name"] for d in result["directories"]] == ["alpha", "beta"]
        assert [f["name"] for f in result["files"]] == ["a.py", "z.py"]

    def test_omits_files_unless_asked(self, browse_tree: Path):
        assert "files" not in FsToolingMixin().browse_repo(str(browse_tree))

    def test_reads_the_directory_once(self, browse_tree: Path, monkeypatch):
        """The single-pass traversal is the point of browse_repo; sharing the
        helpers must not cost a second scandir."""
        from quodeq.data.fs.report_parser import safe_read_dir as real

        calls = []
        monkeypatch.setattr(
            "quodeq.services._browse_mixin.safe_read_dir",
            lambda path: (calls.append(path), real(path))[1],
        )

        FsToolingMixin().browse_repo(str(browse_tree), include_files=True)

        assert calls.count(browse_tree) == 1


class TestListingHelpersSkipUnreadableEntries:
    """A symlink loop must not abort the listing for its siblings."""
    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
    def test_symlink_loop_is_skipped_real_entries_still_listed(self, tmp_path: Path):
        (tmp_path / "a").symlink_to(tmp_path / "b")
        (tmp_path / "b").symlink_to(tmp_path / "a")
        (tmp_path / "real_dir").mkdir()
        (tmp_path / "real_file.txt").write_text("x")

        dirs = FsToolingMixin._list_directories(tmp_path)
        files = FsToolingMixin._list_files(tmp_path)

        assert [d["name"] for d in dirs] == ["real_dir"]
        assert [f["name"] for f in files] == ["real_file.txt"]


class TestListingHelpersAcceptPreReadEntries:
    def test_list_directories_uses_supplied_entries(self, tmp_path: Path):
        import os
        (tmp_path / "keep").mkdir()
        (tmp_path / "drop").mkdir()
        entries = [e for e in os.scandir(tmp_path) if e.name == "keep"]

        dirs = FsToolingMixin._list_directories(tmp_path, entries)

        assert [d["name"] for d in dirs] == ["keep"]

    def test_list_files_uses_supplied_entries(self, tmp_path: Path):
        import os
        (tmp_path / "keep.py").write_text("pass")
        (tmp_path / "drop.py").write_text("pass")
        entries = [e for e in os.scandir(tmp_path) if e.name == "keep.py"]

        files = FsToolingMixin._list_files(tmp_path, entries)

        assert [f["name"] for f in files] == ["keep.py"]


class TestBrowseMkdirFailure:
    """The mkdir error branches return a payload; none of them may raise."""

    def test_os_error_returns_mkdir_failed_and_warns(self, tmp_path: Path, monkeypatch):
        """A permission failure must come back as MKDIR_FAILED, not propagate.

        Pins the sink too: the warning is the only trace of why the call
        failed, and an unbound one would turn this branch into a NameError
        that reaches the route.
        """
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        def _denied(self, *args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(Path, "mkdir", _denied)
        mixin = FsToolingMixin()
        warnings: list[str] = []
        mixin._browse_log = SimpleNamespace(warning=warnings.append)

        result = mixin.browse_mkdir(str(tmp_path), "new-folder")

        assert result == {"error": "Could not create folder", "error_code": "MKDIR_FAILED"}
        assert warnings == ["Could not create folder new-folder: [Errno 13] Permission denied"]

    def test_the_production_mixin_binds_a_real_sink(self):
        """A bare FsBrowseMixin is silent; the tooling mixin must not be."""
        assert FsToolingMixin()._browse_log is SHARED_LOG

    def test_existing_folder_returns_already_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / "taken").mkdir()

        result = FsToolingMixin().browse_mkdir(str(tmp_path), "taken")

        assert result == {"error": "Folder already exists", "error_code": "ALREADY_EXISTS"}

    def test_creates_the_folder_when_nothing_is_in_the_way(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        result = FsToolingMixin().browse_mkdir(str(tmp_path), "fresh")

        assert result == {"created": True, "path": str(tmp_path / "fresh")}
        assert (tmp_path / "fresh").is_dir()
