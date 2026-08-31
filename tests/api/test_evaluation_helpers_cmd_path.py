"""Tests for the aiCmdPath (binary override) validation at the API boundary."""
from __future__ import annotations

import os
import stat
from http import HTTPStatus
from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api._evaluation_helpers import _validate_ai_cmd_path


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture
def bin_dir(tmp_path, monkeypatch):
    """A tmp directory placed on PATH, so binaries in it satisfy the
    on-PATH requirement while binaries elsewhere in tmp_path do not."""
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", f"{d}{os.pathsep}{os.environ.get('PATH', '')}")
    return d


def _make_executable(directory, name: str) -> str:
    if os.name == "nt":
        # shutil.which on Windows only finds PATHEXT extensions.
        path = directory / f"{name}.bat"
        path.write_text("@exit /b 0\n")
        return str(path)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


class TestValidateAiCmdPath:
    def test_absent_override_is_valid(self, app_ctx):
        assert _validate_ai_cmd_path("claude", None) is None
        assert _validate_ai_cmd_path("claude", "") is None

    def test_accepts_absolute_path_on_path_dir(self, app_ctx, bin_dir):
        binary = _make_executable(bin_dir, "claude-api")
        assert _validate_ai_cmd_path("claude", binary) is None

    def test_accepts_bare_name_on_path(self, app_ctx, bin_dir):
        _make_executable(bin_dir, "claude-api")
        assert _validate_ai_cmd_path("claude", "claude-api") is None

    def test_rejects_shell_metacharacters(self, app_ctx):
        resp, status = _validate_ai_cmd_path("claude", "claude;rm -rf /")
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_dotdot_segments(self, app_ctx, bin_dir):
        binary = _make_executable(bin_dir, "claude-api")
        traversal = os.path.join(os.path.dirname(binary), "..", "bin", "claude-api")
        resp, status = _validate_ai_cmd_path("claude", traversal)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_relative_path_with_separator(self, app_ctx, bin_dir):
        _make_executable(bin_dir, "claude-api")
        resp, status = _validate_ai_cmd_path("claude", "bin/claude-api")
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_basename_without_provider_prefix(self, app_ctx, bin_dir):
        binary = _make_executable(bin_dir, "notclaude")
        resp, status = _validate_ai_cmd_path("claude", binary)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_arbitrary_system_binary(self, app_ctx):
        # The allow-list posture: /api must not be able to spawn any program.
        resp, status = _validate_ai_cmd_path("claude", "/bin/sh")
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_executable_outside_path_dirs(self, app_ctx, bin_dir, tmp_path):
        # e.g. a file planted in /tmp or a downloads folder: executable and
        # correctly named, but its directory is not on PATH.
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        binary = _make_executable(outside, "claude-api")
        resp, status = _validate_ai_cmd_path("claude", binary)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_missing_binary(self, app_ctx, bin_dir):
        missing = str(bin_dir / "claude-nowhere")
        resp, status = _validate_ai_cmd_path("claude", missing)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_non_executable_file(self, app_ctx, bin_dir):
        path = bin_dir / "claude-api"
        path.write_text("not executable")
        if os.name != "posix":
            pytest.skip("executable-bit check is POSIX-only")
        resp, status = _validate_ai_cmd_path("claude", str(path))
        assert status == HTTPStatus.BAD_REQUEST

    @patch("quodeq.api._evaluation_helpers._get_ai_cmd", return_value="claude")
    def test_provider_falls_back_to_configured_cmd(self, _mock, app_ctx, bin_dir):
        binary = _make_executable(bin_dir, "claude-api")
        assert _validate_ai_cmd_path(None, binary) is None
