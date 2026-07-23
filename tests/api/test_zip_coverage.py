"""Tests for quodeq.api.zip — zip export helpers."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestMaxZipSizeBytes:
    def test_default(self):
        from quodeq.api.zip import _max_zip_size_bytes
        assert _max_zip_size_bytes() == 500 * 1024 * 1024

    def test_explicit_max_mb(self):
        from quodeq.api.zip import _max_zip_size_bytes
        assert _max_zip_size_bytes(max_mb=10) == 10 * 1024 * 1024

    def test_from_env(self):
        from quodeq.api.zip import _max_zip_size_bytes
        assert _max_zip_size_bytes(env={"QUODEQ_MAX_ZIP_SIZE_MB": "100"}) == 100 * 1024 * 1024

    def test_invalid_env(self):
        from quodeq.api.zip import _max_zip_size_bytes
        result = _max_zip_size_bytes(env={"QUODEQ_MAX_ZIP_SIZE_MB": "bad"})
        assert result == 500 * 1024 * 1024

    def test_env_not_set(self):
        from quodeq.api.zip import _max_zip_size_bytes
        result = _max_zip_size_bytes(env={})
        assert result == 500 * 1024 * 1024


class TestBuildProjectZip:
    def test_creates_zip(self, tmp_path):
        from quodeq.api.zip import _build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "file.txt").write_text("hello")
        (project / "sub").mkdir()
        (project / "sub" / "nested.txt").write_text("world")

        with patch("quodeq.api.zip._max_zip_size_bytes", return_value=10 * 1024 * 1024):
            result = _build_project_zip(project)
            assert result.exists()
            assert result.suffix == ".zip"
            with zipfile.ZipFile(result) as zf:
                names = zf.namelist()
                assert any("file.txt" in n for n in names)
                assert any("nested.txt" in n for n in names)
            os.unlink(result)

    def test_skips_symlinks(self, tmp_path):
        from quodeq.api.zip import _build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "real.txt").write_text("content")
        (project / "link.txt").symlink_to(project / "real.txt")

        with patch("quodeq.api.zip._max_zip_size_bytes", return_value=10 * 1024 * 1024):
            result = _build_project_zip(project)
            with zipfile.ZipFile(result) as zf:
                names = zf.namelist()
                assert not any("link.txt" in n for n in names)
            os.unlink(result)

    def test_size_limit_exceeded(self, tmp_path):
        from quodeq.api.zip import _build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "big.txt").write_text("x" * 1000)

        with patch("quodeq.api.zip._max_zip_size_bytes", return_value=10):
            with pytest.raises(ValueError, match="exceeds maximum"):
                _build_project_zip(project)

    def test_limit_applies_to_compressed_size(self, tmp_path):
        # 1 MB of repeated text deflates to ~1 KB. The cap is on the archive
        # size, so this must export even though the input exceeds the limit.
        from quodeq.api.zip import _build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "big.txt").write_text("x" * (1024 * 1024))

        with patch("quodeq.api.zip._max_zip_size_bytes", return_value=64 * 1024):
            result = _build_project_zip(project)
            assert result.exists()
            assert result.stat().st_size <= 64 * 1024
            os.unlink(result)

    def test_incompressible_data_over_limit_raises(self, tmp_path):
        from quodeq.api.zip import _build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "blob.bin").write_bytes(os.urandom(256 * 1024))

        with patch("quodeq.api.zip._max_zip_size_bytes", return_value=64 * 1024):
            with pytest.raises(ValueError, match="exceeds maximum"):
                _build_project_zip(project)


class TestExportProjectZip:
    def test_invalid_project_path_traversal(self, tmp_path):
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            resp = export_project_zip("../../etc", str(tmp_path))
            if isinstance(resp, tuple):
                _, status = resp
                assert status in (400, 404)

    def test_project_not_found(self, tmp_path):
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            resp = export_project_zip("nonexistent", str(tmp_path))
            if isinstance(resp, tuple):
                _, status = resp
                assert status == 404

    def test_project_too_large(self, tmp_path):
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        project = tmp_path / "big"
        project.mkdir()
        (project / "file.txt").write_text("x" * 100)

        app = Flask(__name__)
        with app.app_context():
            with patch("quodeq.api.zip._build_project_zip", side_effect=ValueError("too big")):
                resp = export_project_zip("big", str(tmp_path))
                if isinstance(resp, tuple):
                    _, status = resp
                    assert status == 413

    def test_os_error(self, tmp_path):
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        project = tmp_path / "broken"
        project.mkdir()

        app = Flask(__name__)
        with app.app_context():
            with patch("quodeq.api.zip._build_project_zip", side_effect=OSError("disk error")):
                resp = export_project_zip("broken", str(tmp_path))
                if isinstance(resp, tuple):
                    _, status = resp
                    assert status == 500
