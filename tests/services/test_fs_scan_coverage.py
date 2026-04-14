"""Extended tests for quodeq.services._fs_scan — edge cases and more coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from quodeq.services._fs_scan import (
    _list_branches,
    _list_modules,
    _walk_files,
    _write_scan_json,
    scan_project,
)
from quodeq.core.types.scan import ScanData


class TestWalkFiles:
    def test_empty_directory(self, tmp_path):
        assert list(_walk_files(tmp_path)) == []

    def test_flat_files(self, tmp_path):
        (tmp_path / "a.py").write_text("pass")
        (tmp_path / "b.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 2

    def test_nested_files(self, tmp_path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (tmp_path / "main.py").write_text("pass")
        (sub / "mod.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 2

    def test_skips_git(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("x")
        (tmp_path / "app.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1
        assert all(".git" not in str(f) for f in files)

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "pkg.js").write_text("x")
        (tmp_path / "index.js").write_text("x")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1

    def test_skips_pycache(self, tmp_path):
        pc = tmp_path / "__pycache__"
        pc.mkdir()
        (pc / "mod.pyc").write_text("x")
        (tmp_path / "mod.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1

    def test_skips_venv(self, tmp_path):
        for d in [".venv", "venv"]:
            venv = tmp_path / d
            venv.mkdir()
            (venv / "activate").write_text("x")
        (tmp_path / "app.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1

    def test_skips_dotdirs(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret").write_text("x")
        (tmp_path / "visible.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1

    def test_skips_build_dirs(self, tmp_path):
        for d in ["dist", "build", ".eggs", ".tox"]:
            bd = tmp_path / d
            bd.mkdir()
            (bd / "artifact").write_text("x")
        (tmp_path / "src.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        assert len(files) == 1

    def test_sorted_output(self, tmp_path):
        (tmp_path / "z.py").write_text("pass")
        (tmp_path / "a.py").write_text("pass")
        (tmp_path / "m.py").write_text("pass")
        files = list(_walk_files(tmp_path))
        names = [f.name for f in files]
        assert names == sorted(names)


class TestListBranches:
    def test_no_git_dir(self, tmp_path):
        assert _list_branches(tmp_path) == []

    def test_git_failure(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("quodeq.services._fs_scan.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert _list_branches(tmp_path) == []

    def test_timeout(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("quodeq.services._fs_scan.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            assert _list_branches(tmp_path) == []

    def test_os_error(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("quodeq.services._fs_scan.subprocess.run", side_effect=OSError("fail")):
            assert _list_branches(tmp_path) == []

    def test_parses_branches(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("quodeq.services._fs_scan.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="main\nfeature/x\n  develop  \n")
            branches = _list_branches(tmp_path)
            assert branches == ["main", "feature/x", "develop"]

    def test_empty_lines_filtered(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("quodeq.services._fs_scan.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="\n\n  \n")
            assert _list_branches(tmp_path) == []


class TestListModules:
    def test_empty(self, tmp_path):
        assert _list_modules(tmp_path) == []

    def test_skips_hidden(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        assert _list_modules(tmp_path) == ["visible"]

    def test_skips_known_dirs(self, tmp_path):
        for d in ["node_modules", "__pycache__", ".git"]:
            (tmp_path / d).mkdir()
        (tmp_path / "src").mkdir()
        assert _list_modules(tmp_path) == ["src"]

    def test_files_excluded(self, tmp_path):
        (tmp_path / "README.md").write_text("x")
        (tmp_path / "src").mkdir()
        assert _list_modules(tmp_path) == ["src"]

    def test_sorted(self, tmp_path):
        for d in ["z_mod", "a_mod", "m_mod"]:
            (tmp_path / d).mkdir()
        result = _list_modules(tmp_path)
        assert result == ["a_mod", "m_mod", "z_mod"]


class TestWriteScanJson:
    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "output"
        scan = ScanData(
            file_tree=["a.py"], languages={"py": 1},
            branches=["main"], modules=["src"],
            scanned_at="2024-01-01T00:00:00Z", total_files=1,
        )
        _write_scan_json(scan, out)
        assert (out / "scan.json").exists()
        data = json.loads((out / "scan.json").read_text())
        assert data["total_files"] == 1

    def test_overwrites_existing(self, tmp_path):
        scan1 = ScanData(file_tree=[], languages={}, branches=[], modules=[], scanned_at="t1", total_files=0)
        scan2 = ScanData(file_tree=["x.py"], languages={"py": 1}, branches=[], modules=[], scanned_at="t2", total_files=1)
        _write_scan_json(scan1, tmp_path)
        _write_scan_json(scan2, tmp_path)
        data = json.loads((tmp_path / "scan.json").read_text())
        assert data["total_files"] == 1


class TestScanProjectExtended:
    def test_language_counting(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "a.py").write_text("pass")
        (project / "b.py").write_text("pass")
        (project / "c.js").write_text("x")
        (project / "d.ts").write_text("x")
        (project / "Makefile").write_text("all:")  # no extension
        result = scan_project(project)
        assert result.languages["py"] == 2
        assert result.languages["js"] == 1
        assert result.languages["ts"] == 1
        assert result.total_files == 5

    def test_deep_nesting(self, tmp_path):
        project = tmp_path / "proj"
        deep = project / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("pass")
        result = scan_project(project)
        assert "a/b/c/deep.py" in result.file_tree

    def test_output_dir_created(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "x.py").write_text("pass")
        out = tmp_path / "new_output"
        scan_project(project, output_dir=out)
        assert (out / "scan.json").exists()
