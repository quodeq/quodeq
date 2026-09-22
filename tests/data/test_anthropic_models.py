"""The Anthropic models-list adapter is the single place that calls the
Anthropic HTTP API to discover Claude model ids. URL/version/timeout arrive
as parameters; env/config resolution stays in ``services/tooling_mixin.py``.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch


class TestFetchAnthropicModels:
    def test_returns_model_ids_on_success(self):
        from quodeq.data.anthropic_models import fetch_anthropic_models

        payload = json.dumps({"data": [{"id": "claude-a"}, {"id": "claude-b"}]}).encode()
        resp = MagicMock()
        resp.read.return_value = payload
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            models = fetch_anthropic_models(
                "key", url="https://api.example/v1/models", version="v1", timeout_s=8,
            )
        assert models == ["claude-a", "claude-b"]

    def test_empty_data_returns_none(self):
        from quodeq.data.anthropic_models import fetch_anthropic_models

        payload = json.dumps({"data": []}).encode()
        resp = MagicMock()
        resp.read.return_value = payload
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            assert fetch_anthropic_models(
                "key", url="https://api.example/v1/models", version="v1", timeout_s=8,
            ) is None

    def test_url_error_returns_none(self):
        from quodeq.data.anthropic_models import fetch_anthropic_models

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            assert fetch_anthropic_models(
                "key", url="https://api.example/v1/models", version="v1", timeout_s=8,
            ) is None

    def test_bad_json_returns_none(self):
        from quodeq.data.anthropic_models import fetch_anthropic_models

        resp = MagicMock()
        resp.read.return_value = b"not json"
        resp.__enter__.return_value = resp
        with patch("urllib.request.urlopen", return_value=resp):
            assert fetch_anthropic_models(
                "key", url="https://api.example/v1/models", version="v1", timeout_s=8,
            ) is None
