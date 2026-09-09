"""_build_evaluation_options: apiKey payload handling and the stored-key fallback."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.api._evaluation_helpers import _build_evaluation_options


class TestApiKeyFromPayload:
    def test_payload_api_key_used_as_is(self):
        with patch("quodeq.api._evaluation_helpers.get_api_key_secure") as mock:
            opts = _build_evaluation_options({"aiCmd": "claude", "apiKey": "sk-from-payload"})
        assert opts.provider_api_key == "sk-from-payload"
        mock.assert_not_called()

    def test_no_ai_cmd_no_api_key_defaults_to_empty(self):
        with patch("quodeq.api._evaluation_helpers.get_api_key_secure") as mock:
            opts = _build_evaluation_options({})
        assert opts.provider_api_key == ""
        mock.assert_not_called()


class TestApiKeyStoredFallback:
    def test_absent_api_key_falls_back_to_stored_key(self):
        with patch("quodeq.api._evaluation_helpers.get_api_key_secure") as mock:
            mock.return_value = "sk-from-store"
            opts = _build_evaluation_options({"aiCmd": "claude"})
        assert opts.provider_api_key == "sk-from-store"
        mock.assert_called_once_with("claude")

    def test_absent_api_key_no_stored_key_defaults_to_empty(self):
        with patch("quodeq.api._evaluation_helpers.get_api_key_secure") as mock:
            mock.return_value = None
            opts = _build_evaluation_options({"aiCmd": "claude"})
        assert opts.provider_api_key == ""
        mock.assert_called_once_with("claude")

    def test_empty_string_api_key_treated_as_absent(self):
        with patch("quodeq.api._evaluation_helpers.get_api_key_secure") as mock:
            mock.return_value = "sk-from-store"
            opts = _build_evaluation_options({"aiCmd": "claude", "apiKey": ""})
        assert opts.provider_api_key == "sk-from-store"
        mock.assert_called_once_with("claude")
