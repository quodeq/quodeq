"""Shared fixtures for tests/api/test_assistant_routes*.py siblings."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.data.sqlite.assistant_repository import AssistantRepository


_VALID_STANDARD = {
    "id": "api-errors", "name": "API Error Contract", "description": "d",
    "weight": 1.0, "source": "assistant",
    "principles": [{"name": "P1", "description": "", "requirements": [
        {"id": "r1", "text": "Endpoints return RFC7807", "description": "", "refs": []},
    ]}],
}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    # deterministic provider catalog for tests
    # NOTE: real get_provider_configs() (quodeq.llm_bridge / analysis.provider_cache)
    # returns dict[str, dict] keyed by provider id, not {"providers": [...]}.
    # See src/quodeq/analysis/provider_cache.py:67 and
    # src/quodeq/data/config/ai_providers.json (top-level keys are provider ids).
    catalog = {
        "ollama": {"type": "api", "api_base": "http://localhost:11434/v1"},
        "claude": {"type": "cli"},
        "gemini": {"type": "cli"},
    }
    monkeypatch.setattr(
        "quodeq.api.assistant_routes.get_provider_configs", lambda: catalog
    )
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "assistant.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "evaluators")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "compiled")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "dimensions.json")
    register_assistant_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _repo(app):
    return AssistantRepository(app.config["ASSISTANT_DB_PATH"])
