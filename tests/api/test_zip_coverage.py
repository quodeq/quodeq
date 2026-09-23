"""Tests for quodeq.api.zip — zip export helpers."""
from __future__ import annotations

import logging
import os
import zipfile
from unittest.mock import patch

import pytest


class TestMaxZipSizeBytes:
    def test_default(self):
        from quodeq.api.zip import max_zip_size_bytes
        assert max_zip_size_bytes() == 500 * 1024 * 1024

    def test_explicit_max_mb(self):
        from quodeq.api.zip import max_zip_size_bytes
        assert max_zip_size_bytes(max_mb=10) == 10 * 1024 * 1024

    def test_from_env(self):
        from quodeq.api.zip import max_zip_size_bytes
        assert max_zip_size_bytes(env={"QUODEQ_MAX_ZIP_SIZE_MB": "100"}) == 100 * 1024 * 1024

    def test_invalid_env(self):
        from quodeq.api.zip import max_zip_size_bytes
        result = max_zip_size_bytes(env={"QUODEQ_MAX_ZIP_SIZE_MB": "bad"})
        assert result == 500 * 1024 * 1024

    def test_env_not_set(self):
        from quodeq.api.zip import max_zip_size_bytes
        result = max_zip_size_bytes(env={})
        assert result == 500 * 1024 * 1024

    def test_invalid_env_logs_warning_naming_the_variable(self, caplog):
        from quodeq.api.zip import max_zip_size_bytes
        with caplog.at_level(logging.WARNING, logger="quodeq.api.zip"):
            result = max_zip_size_bytes(env={"QUODEQ_MAX_ZIP_SIZE_MB": "bogus"})
        assert result == 500 * 1024 * 1024
        messages = [r.getMessage() for r in caplog.records]
        assert any(
            "QUODEQ_MAX_ZIP_SIZE_MB" in m and "bogus" in m and "500" in m for m in messages
        )

    def test_missing_env_stays_silent(self, caplog):
        from quodeq.api.zip import max_zip_size_bytes
        with caplog.at_level(logging.WARNING, logger="quodeq.api.zip"):
            max_zip_size_bytes(env={})
        assert caplog.records == []


class TestZipSizeLimitError:
    def test_public_message_matches_str(self):
        # _ZipSizeLimitError.__init__ passes the same text to super().__init__
        # and to public_message, so the two stay in lockstep; the route must
        # still read public_message (never str(exc)) per
        # tests/api/test_no_exception_echo.py's zero baseline.
        from quodeq.api.zip import _ZipSizeLimitError
        exc = _ZipSizeLimitError("boom, see remediation")
        assert exc.public_message == str(exc) == "boom, see remediation"


class TestBuildProjectZip:
    def test_creates_zip(self, tmp_path):
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "file.txt").write_text("hello")
        (project / "sub").mkdir()
        (project / "sub" / "nested.txt").write_text("world")

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=10 * 1024 * 1024):
            result = build_project_zip(project)
            assert result.exists()
            assert result.suffix == ".zip"
            with zipfile.ZipFile(result) as zf:
                names = zf.namelist()
                assert any("file.txt" in n for n in names)
                assert any("nested.txt" in n for n in names)
            os.unlink(result)

    def test_skips_symlinks(self, tmp_path):
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "real.txt").write_text("content")
        (project / "link.txt").symlink_to(project / "real.txt")

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=10 * 1024 * 1024):
            result = build_project_zip(project)
            with zipfile.ZipFile(result) as zf:
                names = zf.namelist()
                assert not any("link.txt" in n for n in names)
            os.unlink(result)

    def test_size_limit_exceeded(self, tmp_path):
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "big.txt").write_text("x" * 1000)

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=10):
            with pytest.raises(ValueError, match="exceeds maximum"):
                build_project_zip(project)

    def test_limit_applies_to_compressed_size(self, tmp_path):
        # 500 KB of repeated text deflates to ~1 KB. The compressed cap is what
        # gates export, so this must succeed even though the uncompressed input
        # (still under the 640 KB uncompressed headroom) far exceeds the 64 KB
        # compressed cap.
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "big.txt").write_text("x" * (500 * 1024))

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=64 * 1024):
            result = build_project_zip(project)
            assert result.exists()
            assert result.stat().st_size <= 64 * 1024
            os.unlink(result)

    def test_incompressible_data_over_limit_raises(self, tmp_path):
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "blob.bin").write_bytes(os.urandom(256 * 1024))

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=64 * 1024):
            with pytest.raises(ValueError, match="exceeds maximum"):
                build_project_zip(project)

    def test_uncompressed_size_over_headroom_raises(self, tmp_path):
        # Highly compressible data can slip under the compressed cap while its
        # uncompressed size exceeds what import accepts (size_limit *
        # EXTRACT_HEADROOM). Export must reject it up front rather than produce
        # an archive that then fails on re-import. 64 KB cap -> 640 KB
        # uncompressed headroom; 800 KB of "x" deflates to ~1 KB (under the
        # compressed cap) but is over the uncompressed cap.
        from quodeq.api.zip import build_project_zip
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "big.txt").write_text("x" * (800 * 1024))

        with patch("quodeq.api.zip.max_zip_size_bytes", return_value=64 * 1024):
            with pytest.raises(ValueError, match="uncompressed"):
                build_project_zip(project)


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
        from quodeq.api.zip import export_project_zip, _ZipSizeLimitError
        from flask import Flask
        project = tmp_path / "big"
        project.mkdir()
        (project / "file.txt").write_text("x" * 100)

        app = Flask(__name__)
        with app.app_context():
            with patch(
                "quodeq.api.zip.build_project_zip",
                side_effect=_ZipSizeLimitError("too big, see remediation"),
            ):
                resp = export_project_zip("big", str(tmp_path))
                assert isinstance(resp, tuple)
                response, status = resp
                assert status == 413
                assert response.get_json()["error"] == "too big, see remediation"

    def test_project_too_large_keeps_the_limit_error_message(self, tmp_path):
        """The response body must keep _ZipLimits' own message (MB figure +
        remediation), not the generic "Project too large to export" text."""
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        project = tmp_path / "big"
        project.mkdir()
        (project / "file.txt").write_text("x" * 1000)

        app = Flask(__name__)
        with app.app_context():
            with patch("quodeq.api.zip.max_zip_size_bytes", return_value=10):
                resp = export_project_zip("big", str(tmp_path))
                assert isinstance(resp, tuple)
                response, status = resp
                assert status == 413
                message = response.get_json()["error"]
                assert "MB" in message
                assert "QUODEQ_MAX_ZIP_SIZE_MB" in message
                assert message != "Project too large to export"

    def test_other_value_error_answers_a_coded_json_body(self, tmp_path, monkeypatch):
        """zipfile raises ValueErrors of its own (for example "ZIP does not
        support timestamps before 1980" from zf.write under the default
        strict_timestamps=True). Those must get the same coded JSON body as an
        OSError, not Flask's default 500 HTML page with no code."""
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        project = tmp_path / "proj"
        project.mkdir()
        (project / "file.txt").write_text("x")

        def _raise_value_error(*_args, **_kwargs):
            raise ValueError("x")

        monkeypatch.setattr(zipfile.ZipFile, "write", _raise_value_error)
        app = Flask(__name__)
        with app.app_context():
            resp = export_project_zip("proj", str(tmp_path))
        assert isinstance(resp, tuple)
        response, status = resp
        assert status == 500
        body = response.get_json()
        assert body["code"] == "EXPORT_ERROR"
        assert "x" != body["error"], "the exception text must not be echoed"

    def test_os_error(self, tmp_path):
        from quodeq.api.zip import export_project_zip
        from flask import Flask
        project = tmp_path / "broken"
        project.mkdir()

        app = Flask(__name__)
        with app.app_context():
            with patch("quodeq.api.zip.build_project_zip", side_effect=OSError("disk error")):
                resp = export_project_zip("broken", str(tmp_path))
                if isinstance(resp, tuple):
                    _, status = resp
                    assert status == 500
