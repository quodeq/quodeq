"""Tests for cloud API provider testing."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

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

        with patch("quodeq.llm_bridge._cloud.openai") as mock_openai:
            mock_openai.OpenAI.return_value = mock_client
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
        mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")
        with patch("quodeq.llm_bridge._cloud.openai") as mock_openai:
            mock_openai.OpenAI.return_value = mock_client
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
