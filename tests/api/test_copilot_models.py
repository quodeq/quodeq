from unittest.mock import Mock

from flask import Flask

from quodeq.api.routes_discovery import register_discovery_routes


def test_model_discovery_error_is_not_a_success_response():
    provider = Mock()
    provider.get_client_models.return_value = {
        "models": [], "error": "Authentication required",
        "error_code": "COPILOT_MODELS_UNAVAILABLE",
    }
    app = Flask(__name__)
    register_discovery_routes(app, provider)
    response = app.test_client().get("/api/ai-clients/copilot/models")
    assert response.status_code == 503
    assert response.json["code"] == "COPILOT_MODELS_UNAVAILABLE"
    assert response.json["error"] == "Authentication required"


def test_model_discovery_success_preserves_existing_response_shape():
    provider = Mock()
    provider.get_client_models.return_value = {"models": ["auto", "gpt-test"]}
    app = Flask(__name__)
    register_discovery_routes(app, provider)
    response = app.test_client().get("/api/ai-clients/copilot/models")
    assert response.status_code == 200
    assert response.json == {"models": ["auto", "gpt-test"]}
