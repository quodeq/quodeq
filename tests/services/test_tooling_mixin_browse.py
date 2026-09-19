"""Tests for tooling_mixin.py: browse-path validation, directory/file listing and browse_repo."""

from __future__ import annotations

from pathlib import Path


from quodeq.services.tooling_mixin import FsToolingMixin


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

    def test_outside_home(self, tmp_path: Path):
        target, err = FsToolingMixin._validate_browse_path("/tmp")
        # /tmp is typically not under $HOME
        if not Path("/tmp").resolve().is_relative_to(Path.home()):
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


class TestBrowseRepoUsesTheListingHelpers:
    """browse_repo must not keep its own copy of the listing rules: it feeds
    one directory read to _list_directories/_list_files."""

    @staticmethod
    def _tree_under_home() -> Path:
        import tempfile
        base = Path(tempfile.mkdtemp(dir=Path.home(), prefix="quodeq_browse_"))
        (base / "beta").mkdir()
        (base / "alpha").mkdir()
        (base / "alpha" / ".git").mkdir()
        (base / ".hidden_dir").mkdir()
        (base / "z.py").write_text("pass")
        (base / "a.py").write_text("pass")
        (base / ".env").write_text("SECRET")
        return base

    def test_matches_the_helpers_exactly(self):
        import shutil
        base = self._tree_under_home()
        try:
            result = FsToolingMixin().browse_repo(str(base), include_files=True)

            assert result["directories"] == FsToolingMixin._list_directories(base)
            assert result["files"] == FsToolingMixin._list_files(base)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_omits_files_unless_asked(self):
        import shutil
        base = self._tree_under_home()
        try:
            assert "files" not in FsToolingMixin().browse_repo(str(base))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_reads_the_directory_once(self, monkeypatch):
        """The single-pass traversal is the point of browse_repo; sharing the
        helpers must not cost a second scandir."""
        import shutil
        import quodeq.services.tooling_mixin as tooling_mixin

        base = self._tree_under_home()
        calls = []
        real = tooling_mixin.safe_read_dir
        monkeypatch.setattr(
            tooling_mixin, "safe_read_dir",
            lambda path: (calls.append(path), real(path))[1],
        )
        try:
            FsToolingMixin().browse_repo(str(base), include_files=True)

            assert calls.count(base) == 1
        finally:
            shutil.rmtree(base, ignore_errors=True)


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
