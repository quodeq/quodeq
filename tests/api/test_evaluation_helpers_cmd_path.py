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


def _make_executable(tmp_path, name: str) -> str:
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


class TestValidateAiCmdPath:
    def test_absent_override_is_valid(self, app_ctx):
        assert _validate_ai_cmd_path("claude", None) is None
        assert _validate_ai_cmd_path("claude", "") is None

    def test_accepts_executable_with_provider_prefix(self, app_ctx, tmp_path):
        binary = _make_executable(tmp_path, "claude-api")
        assert _validate_ai_cmd_path("claude", binary) is None

    def test_rejects_shell_metacharacters(self, app_ctx):
        resp, status = _validate_ai_cmd_path("claude", "claude;rm -rf /")
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_basename_without_provider_prefix(self, app_ctx, tmp_path):
        binary = _make_executable(tmp_path, "notclaude")
        resp, status = _validate_ai_cmd_path("claude", binary)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_arbitrary_system_binary(self, app_ctx):
        # The allow-list posture: /api must not be able to spawn any program.
        resp, status = _validate_ai_cmd_path("claude", "/bin/sh")
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_missing_binary(self, app_ctx, tmp_path):
        missing = str(tmp_path / "claude-nowhere")
        resp, status = _validate_ai_cmd_path("claude", missing)
        assert status == HTTPStatus.BAD_REQUEST

    def test_rejects_non_executable_file(self, app_ctx, tmp_path):
        path = tmp_path / "claude-api"
        path.write_text("not executable")
        if os.name != "posix":
            pytest.skip("executable-bit check is POSIX-only")
        resp, status = _validate_ai_cmd_path("claude", str(path))
        assert status == HTTPStatus.BAD_REQUEST

    @patch("quodeq.api._evaluation_helpers._get_ai_cmd", return_value="claude")
    def test_provider_falls_back_to_configured_cmd(self, _mock, app_ctx, tmp_path):
        binary = _make_executable(tmp_path, "claude-api")
        assert _validate_ai_cmd_path(None, binary) is None
