"""Tests for tooling_mixin.py — AI client discovery and model fetching."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch


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
# get_ai_clients
# ---------------------------------------------------------------------------


class TestGetAiClients:
    @patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={})
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_installed_cli_marked_installed(self, mock_which, mock_cfg):
        mixin = FsToolingMixin()
        result = mixin.get_ai_clients(env={})
        claude = next(c for c in result["clients"] if c["id"] == "claude")
        assert claude["installed"] is True

    @patch("quodeq.services.tooling_mixin.get_provider_configs", return_value={})
    @patch("shutil.which", return_value=None)
    def test_uninstalled_cli_still_listed_with_flag(self, mock_which, mock_cfg):
        mixin = FsToolingMixin()
        result = mixin.get_ai_clients(env={})
        # All default CLI candidates are returned so the UI can render them disabled.
        ids = [c["id"] for c in result["clients"]]
        assert {"claude", "codex", "gemini"} <= set(ids)
        assert all(c["installed"] is False for c in result["clients"])

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

    def test_configure_model_fetchers_routes_claude_to_the_api_fetcher(self):
        mixin = FsToolingMixin()
        assert "claude" not in mixin._model_fetchers
        mixin.configure_model_fetchers()
        assert mixin._model_fetchers["claude"] == mixin._get_claude_models

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

    # #139 — ValueError (e.g. corrupt JSON int parse) must also be caught
    @patch("quodeq.services.tooling_mixin.read_json", side_effect=ValueError("bad int"))
    def test_returns_empty_on_value_error(self, mock_read):
        assert _load_fallback_claude_models() == []
