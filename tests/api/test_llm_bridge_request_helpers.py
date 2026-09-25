"""Request readers shared by the llm_bridge handlers: the object body, the
concurrency-test model request and the ``?base_url=`` query parameter."""
from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.llm_bridge_routes import register_llm_bridge_routes

_BODY_NOT_OBJECT = {"error": "request body must be a JSON object", "code": "INVALID_PARAM"}
_ROUTES = "quodeq.api.llm_bridge_routes"


@pytest.fixture()
def client():
    app = Flask(__name__)
    register_llm_bridge_routes(app)
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("path", [
    "/api/ollama/test-concurrency", "/api/llamacpp/test-concurrency", "/api/omlx/test-concurrency",
    "/api/ollama/estimate-agents", "/api/provider/test", "/api/provider/key",
])
def test_a_non_object_body_answers_400(client, path: str) -> None:
    resp = client.post(path, json=[1])
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json() == _BODY_NOT_OBJECT


def test_the_model_reaches_the_concurrency_test(client) -> None:
    with patch(f"{_ROUTES}.run_concurrency_test", return_value={"ok": True}) as run:
        assert client.post("/api/ollama/test-concurrency", json={"model": "m1"}).get_json() == {"ok": True}
    run.assert_called_once_with("m1")


def test_an_empty_model_is_accepted_where_not_required(client) -> None:
    with patch(f"{_ROUTES}.run_llamacpp_concurrency_test", return_value={"ok": True}) as run:
        assert client.post("/api/llamacpp/test-concurrency", json={}).status_code == HTTPStatus.OK
    run.assert_called_once_with("")


def test_an_empty_model_is_refused_where_required(client) -> None:
    resp = client.post("/api/ollama/test-concurrency", json={})
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()["code"] == "MISSING_PARAM"


@pytest.mark.parametrize("path", ["/api/omlx/status", "/api/omlx/models"])
def test_a_blank_base_url_is_passed_as_none(client, path: str) -> None:
    with patch(f"{_ROUTES}.get_omlx_status", return_value={}) as status, \
         patch(f"{_ROUTES}.list_omlx_models", return_value=[]) as models:
        assert client.get(f"{path}?base_url=%20%20").status_code == HTTPStatus.OK
    called = status if path.endswith("status") else models
    assert called.call_args.kwargs["base_url"] is None


def test_an_accepted_base_url_is_stripped(client) -> None:
    with patch(f"{_ROUTES}.get_omlx_status", return_value={}) as status:
        client.get("/api/omlx/status?base_url=%20http://10.0.0.5:8000%20")
    assert status.call_args.kwargs["base_url"] == "http://10.0.0.5:8000"


@pytest.mark.parametrize("path", ["/api/omlx/status", "/api/omlx/models"])
def test_a_non_http_base_url_is_refused(client, path: str) -> None:
    resp = client.get(f"{path}?base_url=file:///etc/passwd")
    assert resp.status_code == HTTPStatus.BAD_REQUEST
    assert resp.get_json()["code"] == "INVALID_URL"
