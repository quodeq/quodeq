"""Tests for the aiModel requirement on API-type providers."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from flask import Flask

from quodeq.api._evaluation_helpers import _validate_ai_model


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


_CONFIGS = {
    "ollama": {"type": "api"},
    "claude": {"type": "cli"},
}


class TestValidateAiModel:
    def test_api_type_without_model_is_rejected(self, app_ctx):
        result = _validate_ai_model("ollama", None, _CONFIGS)
        assert result is not None
        response, status = result
        assert status == HTTPStatus.BAD_REQUEST
        assert response.get_json() == {
            "error": "No model selected. Go to Settings and select one.",
            "code": "MODEL_REQUIRED",
        }

    def test_api_type_with_model_passes(self, app_ctx):
        assert _validate_ai_model("ollama", "llama3", _CONFIGS) is None

    def test_cli_type_without_model_passes(self, app_ctx):
        assert _validate_ai_model("claude", None, _CONFIGS) is None

    def test_no_ai_cmd_passes(self, app_ctx):
        assert _validate_ai_model(None, None, _CONFIGS) is None

    def test_unknown_provider_passes(self, app_ctx):
        assert _validate_ai_model("mystery", None, _CONFIGS) is None
