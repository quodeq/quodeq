"""Tests for quodeq.assistant.adapters.api._default_client's retry setting.

Split from test_api_adapter.py (already at the 300-line file cap) rather
than growing that file.
"""
from __future__ import annotations

from unittest.mock import patch

import quodeq.assistant.adapters.api as api_module
from quodeq.assistant.adapters.api import ApiTurnConfig


def test_default_client_retries_twice():
    config = ApiTurnConfig(api_base="http://x/v1", api_key=None, model="m", native_tools=True)
    with patch("quodeq.assistant.adapters.api.openai.OpenAI") as mock_openai:
        api_module._default_client(config)
    _args, kwargs = mock_openai.call_args
    assert kwargs["max_retries"] == 2
