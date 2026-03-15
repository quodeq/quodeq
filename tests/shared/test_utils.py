"""Tests for quodeq.shared.utils — configuration accessors and helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.shared import utils


class TestIsRepoUrl:
    def test_https_url(self):
        assert utils.is_repo_url("https://github.com/org/repo") is True

    def test_http_url(self):
        assert utils.is_repo_url("http://github.com/org/repo") is True

    def test_git_ssh_url(self):
        assert utils.is_repo_url("git@github.com:org/repo.git") is True

    def test_local_path(self):
        assert utils.is_repo_url("/Users/me/projects/repo") is False

    def test_relative_path(self):
        assert utils.is_repo_url("./my-repo") is False


class TestProjectNameFromRepo:
    def test_local_path(self):
        assert utils.project_name_from_repo("/home/user/my-project") == "my-project"

    def test_url_strips_git_suffix(self):
        assert utils.project_name_from_repo("https://github.com/org/repo.git") == "repo"

    def test_url_without_git_suffix(self):
        assert utils.project_name_from_repo("https://github.com/org/repo") == "repo"


class TestReadJson:
    def test_reads_valid_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text(json.dumps({"key": "value"}))
        assert utils.read_json(f) == {"key": "value"}

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises((FileNotFoundError, ValueError)):
            utils.read_json(tmp_path / "missing.json")


class TestConfigure:
    def test_overrides_defaults(self):
        with utils._get_config().override(ai_cmd_default="my-cli"):
            assert utils.get_ai_cmd() == "my-cli"

    def test_get_ai_cmd_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_CMD", "env-cli")
        assert utils.get_ai_cmd() == "env-cli"


class TestGetters:
    def test_get_ai_model_none_by_default(self, monkeypatch):
        monkeypatch.delenv("AI_MODEL", raising=False)
        assert utils.get_ai_model() is None

    def test_get_ai_model_from_env(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL", "claude-3")
        assert utils.get_ai_model() == "claude-3"

    def test_get_action_api_port_default(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_ACTION_API_PORT", raising=False)
        assert utils.get_action_api_port() == 8001

    def test_get_action_api_port_from_env(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_ACTION_API_PORT", "9999")
        assert utils.get_action_api_port() == 9999

    def test_get_action_api_host_default(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_ACTION_API_HOST", raising=False)
        assert utils.get_action_api_host() == "127.0.0.1"

    def test_get_evaluations_dir_default(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_EVALUATIONS_DIR", raising=False)
        expected = str(Path.home() / ".quodeq" / "evaluations")
        assert utils.get_evaluations_dir() == expected

    def test_get_evaluations_dir_explicit_default(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_EVALUATIONS_DIR", raising=False)
        assert utils.get_evaluations_dir("evaluations") == "evaluations"

    def test_get_evaluations_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", "/custom/dir")
        assert utils.get_evaluations_dir() == "/custom/dir"

    def test_get_anthropic_api_key_none_by_default(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert utils.get_anthropic_api_key() is None

    def test_get_static_dist_none_by_default(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_STATIC_DIST", raising=False)
        assert utils.get_static_dist() is None


class TestShowDiff:
    def test_no_changes(self, tmp_path, capsys):
        f = tmp_path / "test.txt"
        f.write_text("hello\n")
        utils.show_diff(f, "hello\n")
        assert "[no changes]" in capsys.readouterr().out

    def test_shows_diff(self, tmp_path, capsys):
        f = tmp_path / "test.txt"
        f.write_text("old\n")
        utils.show_diff(f, "new\n")
        output = capsys.readouterr().out
        assert "-old" in output
        assert "+new" in output
