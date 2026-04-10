"""Tests for tooling_mixin.py — browse paths, AI client discovery, model fetching."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.services.tooling_mixin import (
    FsToolingMixin,
    _fetch_anthropic_models,
    _load_fallback_claude_models,
    get_allowed_client_ids,
    _DEFAULT_CLIENT_IDS,
)


# ---------------------------------------------------------------------------
# get_allowed_client_ids
# ---------------------------------------------------------------------------


class TestGetAllowedClientIds:
    @patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={})
    def test_default_ids(self, mock_cfg):
        ids = get_allowed_client_ids(env={})
        assert ids == _DEFAULT_CLIENT_IDS

    def test_env_override(self):
        ids = get_allowed_client_ids(env={"QUODEQ_AI_CLIENTS": "foo,bar"})
        assert ids == frozenset({"foo", "bar"})

    @patch("quodeq.services.tooling_mixin.get_provider_configs")
    def test_includes_api_providers(self, mock_cfg):
        mock_cfg.return_value = {
            "ollama": {"type": "api"},
            "claude": {"type": "cli"},
        }
        ids = get_allowed_client_ids(env={})
        assert "ollama" in ids
        assert "claude" in ids  # from defaults


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


# ---------------------------------------------------------------------------
# get_ai_clients
# ---------------------------------------------------------------------------


class TestGetAiClients:
    @patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={})
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_includes_installed_cli(self, mock_which, mock_cfg):
        mixin = FsToolingMixin()
        result = mixin.get_ai_clients(env={})
        ids = [c["id"] for c in result["clients"]]
        assert "claude" in ids

    @patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={})
    @patch("shutil.which", return_value=None)
    def test_excludes_uninstalled_cli(self, mock_which, mock_cfg):
        mixin = FsToolingMixin()
        result = mixin.get_ai_clients(env={})
        assert result["clients"] == []

    def test_env_override_candidates(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={}):
            with patch("shutil.which", return_value="/usr/bin/custom"):
                result = mixin.get_ai_clients(env={"QUODEQ_AI_CLIENTS": "custom"})
        ids = [c["id"] for c in result["clients"]]
        assert "custom" in ids

    @patch("quodeq.services.tooling_mixin.get_provider_configs")
    @patch("shutil.which", return_value=None)
    def test_custom_provider_excluded(self, mock_which, mock_cfg):
        """The 'custom' provider ID should not appear in clients."""
        mock_cfg.return_value = {"custom": {"type": "api"}, "ollama": {"type": "api"}}
        mixin = FsToolingMixin()
        result = mixin.get_ai_clients(env={})
        ids = [c["id"] for c in result["clients"]]
        assert "custom" not in ids
        assert "ollama" in ids


# ---------------------------------------------------------------------------
# _get_cli_models
# ---------------------------------------------------------------------------


class TestGetCliModels:
    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_returns_models(self, mock_run, mock_which, mock_ids):
        mock_run.return_value = MagicMock(returncode=0, stdout="model-a\nmodel-b\n")
        mixin = FsToolingMixin()
        result = mixin._get_cli_models("claude")
        assert result == {"models": ["model-a", "model-b"]}

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_filters_comment_lines(self, mock_run, mock_which, mock_ids):
        mock_run.return_value = MagicMock(returncode=0, stdout="# Models\nmodel-a\n=====\nmodel-b\n")
        mixin = FsToolingMixin()
        result = mixin._get_cli_models("claude")
        assert result == {"models": ["model-a", "model-b"]}

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset())
    def test_disallowed_client(self, mock_ids):
        mixin = FsToolingMixin()
        assert mixin._get_cli_models("evil") == {"models": []}

    def test_non_alnum_client(self):
        mixin = FsToolingMixin()
        with patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"a;b"})):
            assert mixin._get_cli_models("a;b") == {"models": []}

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value=None)
    def test_not_installed(self, mock_which, mock_ids):
        mixin = FsToolingMixin()
        assert mixin._get_cli_models("claude") == {"models": []}

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=8))
    def test_timeout(self, mock_run, mock_which, mock_ids):
        mixin = FsToolingMixin()
        assert mixin._get_cli_models("claude") == {"models": []}

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_nonzero_returncode(self, mock_run, mock_which, mock_ids):
        mock_run.return_value = MagicMock(returncode=1, stdout="error output")
        mixin = FsToolingMixin()
        assert mixin._get_cli_models("claude") == {"models": []}


# ---------------------------------------------------------------------------
# get_client_models (uses fetcher registry)
# ---------------------------------------------------------------------------


class TestGetClientModels:
    def test_uses_registered_fetcher(self):
        mixin = FsToolingMixin()
        custom_fetcher = MagicMock(return_value={"models": ["custom-model"]})
        mixin._model_fetchers["myapi"] = custom_fetcher
        result = mixin.get_client_models("myapi")
        assert result == {"models": ["custom-model"]}
        custom_fetcher.assert_called_once_with("myapi")

    @patch("quodeq.services.tooling_mixin.get_allowed_client_ids", return_value=frozenset({"claude"}))
    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_falls_back_to_cli(self, mock_run, mock_which, mock_ids):
        mock_run.return_value = MagicMock(returncode=0, stdout="model-x\n")
        mixin = FsToolingMixin()
        result = mixin.get_client_models("claude")
        assert result == {"models": ["model-x"]}


# ---------------------------------------------------------------------------
# _get_claude_models
# ---------------------------------------------------------------------------


class TestGetClaudeModels:
    @patch("quodeq.services.tooling_mixin._fetch_anthropic_models", return_value=["claude-3-opus", "claude-3-sonnet"])
    def test_returns_api_models(self, mock_fetch):
        mixin = FsToolingMixin()
        result = mixin._get_claude_models(api_key="sk-test")
        assert result == {"models": ["claude-3-opus", "claude-3-sonnet"]}

    @patch("quodeq.services.tooling_mixin._fetch_anthropic_models", return_value=None)
    @patch("quodeq.services.tooling_mixin._load_fallback_claude_models", return_value=["fallback-model"])
    def test_falls_back_on_api_failure(self, mock_fallback, mock_fetch):
        mixin = FsToolingMixin()
        result = mixin._get_claude_models(api_key="sk-test")
        assert result == {"models": ["fallback-model"]}

    @patch("quodeq.services.tooling_mixin._load_fallback_claude_models", return_value=["fallback"])
    def test_no_key_uses_fallback(self, mock_fallback):
        mixin = FsToolingMixin()
        result = mixin._get_claude_models(api_key=None, key_fn=lambda: None)
        assert result == {"models": ["fallback"]}


# ---------------------------------------------------------------------------
# _fetch_anthropic_models
# ---------------------------------------------------------------------------


class TestFetchAnthropicModels:
    @patch("urllib.request.urlopen")
    def test_returns_model_ids(self, mock_urlopen):
        response_data = json.dumps({"data": [{"id": "m1"}, {"id": "m2"}]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = _fetch_anthropic_models("sk-test")
        assert result == ["m1", "m2"]

    @patch("urllib.request.urlopen")
    def test_empty_data_returns_none(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"data": []}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        assert _fetch_anthropic_models("sk-test") is None

    @patch("urllib.request.urlopen", side_effect=OSError("network error"))
    def test_network_error_returns_none(self, mock_urlopen):
        assert _fetch_anthropic_models("sk-test") is None


# ---------------------------------------------------------------------------
# _load_fallback_claude_models
# ---------------------------------------------------------------------------


class TestLoadFallbackClaudeModels:
    @patch("quodeq.services.tooling_mixin.read_json")
    def test_returns_model_list(self, mock_read):
        mock_read.return_value = {"fallback_claude_models": ["m1", "m2"]}
        assert _load_fallback_claude_models() == ["m1", "m2"]

    @patch("quodeq.services.tooling_mixin.read_json", side_effect=OSError)
    def test_returns_empty_on_error(self, mock_read):
        assert _load_fallback_claude_models() == []
