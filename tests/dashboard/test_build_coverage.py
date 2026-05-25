"""Tests for quodeq.dashboard._build — UI build orchestration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestMaybeBuildUi:
    # --- Production: wheel-bundled static is authoritative, never invokes npm. ---

    def test_production_returns_bundled_static_when_present(self, tmp_path):
        """Production returns the wheel-bundled static dir without invoking npm."""
        from quodeq.dashboard._build import maybe_build_ui
        bundled = tmp_path / "static"
        bundled.mkdir()
        (bundled / "index.html").write_text("<html></html>")
        with patch("quodeq.dashboard._build._static_dir_bundled", return_value=bundled), \
             patch("quodeq.dashboard._build.run_npm_build") as mock_build:
            result = maybe_build_ui(no_build=False, reinstall=False)
            assert result == bundled
            mock_build.assert_not_called()

    def test_production_raises_when_bundled_static_missing(self, tmp_path):
        """Production never falls back to npm. Missing static must fail loud."""
        from quodeq.dashboard._build import maybe_build_ui
        empty = tmp_path / "static"
        empty.mkdir()
        with patch("quodeq.dashboard._build._static_dir_bundled", return_value=empty):
            with pytest.raises(FileNotFoundError, match="UI static assets are missing"):
                maybe_build_ui(no_build=False, reinstall=False)

    def test_production_ignores_no_build_flag(self, tmp_path):
        """no_build is irrelevant in production since npm is never invoked."""
        from quodeq.dashboard._build import maybe_build_ui
        bundled = tmp_path / "static"
        bundled.mkdir()
        (bundled / "index.html").write_text("<html></html>")
        with patch("quodeq.dashboard._build._static_dir_bundled", return_value=bundled):
            assert maybe_build_ui(no_build=True, reinstall=False) == bundled
            assert maybe_build_ui(no_build=False, reinstall=False) == bundled

    # --- Dev mode: source-aware rebuild loop, contributor workflow. ---

    def test_dev_no_build_with_cache(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        dev_source = tmp_path / "dev_source"
        dev_source.mkdir()
        dev_static = tmp_path / "dev_static"
        dev_static.mkdir()
        (dev_static / "index.html").write_text("<html></html>")
        with patch("quodeq.dashboard._build.resolve_dev_source", return_value=dev_source), \
             patch("quodeq.dashboard._build._dev_static_dir", return_value=dev_static):
            result = maybe_build_ui(no_build=True, reinstall=False, dev=True)
            assert result == dev_static

    def test_dev_no_build_without_cache(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        dev_source = tmp_path / "dev_source"
        dev_source.mkdir()
        dev_static = tmp_path / "dev_static"
        with patch("quodeq.dashboard._build.resolve_dev_source", return_value=dev_source), \
             patch("quodeq.dashboard._build._dev_static_dir", return_value=dev_static):
            with pytest.raises(FileNotFoundError, match="No cached"):
                maybe_build_ui(no_build=True, reinstall=False, dev=True)

    def test_dev_skip_when_up_to_date(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        dev_source = tmp_path / "dev_source"
        dev_source.mkdir()
        dev_static = tmp_path / "dev_static"
        with patch("quodeq.dashboard._build.resolve_dev_source", return_value=dev_source), \
             patch("quodeq.dashboard._build._dev_static_dir", return_value=dev_static), \
             patch("quodeq.dashboard._build.needs_rebuild", return_value=False), \
             patch("quodeq.dashboard._build.run_npm_build") as mock_build:
            result = maybe_build_ui(no_build=False, reinstall=False, dev=True)
            assert result == dev_static
            mock_build.assert_not_called()

    def test_dev_rebuilds_when_needed(self, tmp_path):
        from quodeq.dashboard._build import maybe_build_ui
        dev_source = tmp_path / "dev_source"
        dev_source.mkdir()
        dev_static = tmp_path / "dev_static"
        with patch("quodeq.dashboard._build.resolve_dev_source", return_value=dev_source), \
             patch("quodeq.dashboard._build._dev_static_dir", return_value=dev_static), \
             patch("quodeq.dashboard._build.needs_rebuild", return_value=True), \
             patch("quodeq.dashboard._build.run_npm_build") as mock_build, \
             patch("quodeq.dashboard._build.compute_source_hash", return_value="abc123"):
            result = maybe_build_ui(no_build=False, reinstall=False, dev=True)
            assert result == dev_static
            mock_build.assert_called_once()


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
