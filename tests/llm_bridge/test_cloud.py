"""Tests for cloud API provider testing."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import httpx
import openai

from quodeq.llm_bridge._cloud import check_cloud_connection


class TestCloudConnection:
    def test_successful_connection(self):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_choice = MagicMock()
        mock_choice.message.content = "hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        # Patches only the OpenAI client constructor, not the whole `openai`
        # module: check_cloud_connection's except now names openai.OpenAIError
        # directly, so that name must stay the real exception class.
        with patch("openai.OpenAI", return_value=mock_client):
            result = check_cloud_connection(
                api_base="https://openrouter.ai/api/v1",
                model="test-model",
                api_key="sk-test",
            )

        assert result["success"] is True
        assert "latency_ms" in result
        mock_client.__exit__.assert_called_once()

    def test_auth_failure(self):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        # A real openai.OpenAIError subclass, not a bare Exception: the
        # except was narrowed to (openai.OpenAIError, httpx.HTTPError)
        # (R-FT-7) -- what the openai SDK actually raises for a failed call.
        mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
            message="401 Unauthorized", request=httpx.Request("GET", "https://example.com"),
        )
        with patch("openai.OpenAI", return_value=mock_client):
            result = check_cloud_connection(
                api_base="https://openrouter.ai/api/v1",
                model="test-model",
                api_key="bad-key",
            )

        assert result["success"] is False
        assert "401" in result["error"]
        mock_client.__exit__.assert_called_once()

    def test_missing_openai_package(self):
        with patch("quodeq.llm_bridge._cloud.openai", None):
            result = check_cloud_connection(
                api_base="https://example.com/v1",
                model="test",
                api_key="test",
            )

        assert result["success"] is False
        assert "openai" in result["error"].lower()

    def test_client_has_a_short_timeout_and_no_retries(self):
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        with patch("openai.OpenAI", return_value=mock_client) as mock_openai_cls:
            check_cloud_connection(
                api_base="https://openrouter.ai/api/v1",
                model="test-model",
                api_key="sk-test",
            )

        _args, kwargs = mock_openai_cls.call_args
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"].read == 30.0
