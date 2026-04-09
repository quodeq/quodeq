"""Tests for quodeq.dashboard._build — UI build orchestration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestMaybeBuildUi:
    def test_no_build_with_cache(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        with patch("quodeq.dashboard._build._static_dir", return_value=tmp_path):
            (tmp_path / "index.html").write_text("<html></html>")
            result = maybe_build_ui(no_build=True, reinstall=False)
            assert result == tmp_path

    def test_no_build_without_cache(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        with patch("quodeq.dashboard._build._static_dir", return_value=tmp_path):
            with pytest.raises(FileNotFoundError, match="No cached"):
                maybe_build_ui(no_build=True, reinstall=False)

    def test_skip_when_up_to_date(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        with patch("quodeq.dashboard._build._get_ui_source_dir", return_value=tmp_path), \
             patch("quodeq.dashboard._build._static_dir", return_value=tmp_path), \
             patch("quodeq.dashboard._build.needs_rebuild", return_value=False):
            result = maybe_build_ui(no_build=False, reinstall=False)
            assert result == tmp_path

    def test_rebuilds_when_needed(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        source = tmp_path / "source"
        source.mkdir()
        static = tmp_path / "static"
        with patch("quodeq.dashboard._build._get_ui_source_dir", return_value=source), \
             patch("quodeq.dashboard._build._static_dir", return_value=static), \
             patch("quodeq.dashboard._build.needs_rebuild", return_value=True), \
             patch("quodeq.dashboard._build._build_workdir", return_value=tmp_path / "work"), \
             patch("quodeq.dashboard._build.sync_source_to_workdir"), \
             patch("quodeq.dashboard._build.run_npm_build"), \
             patch("quodeq.dashboard._build.compute_source_hash", return_value="abc123"):
            result = maybe_build_ui(no_build=False, reinstall=False)
            assert result == static

    def test_dev_mode(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        dev_source = tmp_path / "dev_source"
        dev_source.mkdir()
        dev_static = tmp_path / "dev_static"
        with patch("quodeq.dashboard._build.resolve_dev_source", return_value=dev_source), \
             patch("quodeq.dashboard._build._dev_static_dir", return_value=dev_static), \
             patch("quodeq.dashboard._build.run_npm_build"), \
             patch("quodeq.dashboard._build.compute_source_hash", return_value="def456"):
            result = maybe_build_ui(no_build=False, reinstall=False, dev=True)
            assert result == dev_static


class TestBuildNpmHelpers:
    def test_quodeq_dir_default(self):
        from quodeq.dashboard._build_npm import _quodeq_dir
        result = _quodeq_dir(env={})
        assert result == Path.home() / ".quodeq"

    def test_quodeq_dir_from_env(self, tmp_path):
        from quodeq.dashboard._build_npm import _quodeq_dir
        result = _quodeq_dir(env={"QUODEQ_DIR": str(tmp_path)})
        assert result == tmp_path

    def test_sync_source_to_workdir(self, tmp_path):
        from quodeq.dashboard._build_npm import sync_source_to_workdir
        source = tmp_path / "source"
        source.mkdir()
        (source / "src").mkdir()
        (source / "src" / "file.ts").write_text("code")
        (source / "package.json").write_text("{}")
        workdir = tmp_path / "workdir"
        with patch("quodeq.dashboard._build_npm._SYNC_ITEMS", ["src", "package.json"]):
            sync_source_to_workdir(source, workdir)
            assert (workdir / "package.json").exists()
            assert (workdir / "src" / "file.ts").exists()

    def test_run_npm_build_missing_npm(self, tmp_path):
        from quodeq.dashboard._build_npm import run_npm_build
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="npm"):
                run_npm_build(tmp_path, tmp_path / "static")

    def test_resolve_dev_source_not_found(self, tmp_path):
        from quodeq.dashboard._build_npm import resolve_dev_source
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            with pytest.raises(FileNotFoundError, match="Cannot find"):
                resolve_dev_source()

    def test_resolve_dev_source_found(self, tmp_path):
        from quodeq.dashboard._build_npm import resolve_dev_source
        ui_dir = tmp_path / "ui" / "web"
        ui_dir.mkdir(parents=True)
        (ui_dir / "package.json").write_text("{}")
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            result = resolve_dev_source()
            assert result == ui_dir
