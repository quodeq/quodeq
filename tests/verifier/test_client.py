import json

import httpx
import pytest

from quodeq.verifier.client import OllamaClient
from quodeq.verifier.errors import (
    MalformedResponseError,
    OllamaUnreachableError,
    VerifierTimeoutError,
)


def _stub_transport(handler):
    return httpx.MockTransport(handler)


def test_client_returns_parsed_json_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "message": {
                "content": json.dumps(
                    {
                        "checklist": {q: {"answer": "yes", "cite": None} for q in ("Q1", "Q2", "Q3", "Q4", "Q5")},
                        "findings": {
                            "default_implementation": {"value": "X", "cite": None},
                            "override_mechanism": {"value": "y", "cite": None},
                            "abstraction_in_use": {"value": "Z", "cite": None},
                        },
                        "confidence": 0.5,
                        "evidence_summary": "ok",
                    }
                )
            }
        }
        return httpx.Response(200, json=body)

    client = OllamaClient(base_url="http://test", transport=_stub_transport(handler))
    out = client.chat(system="sys", user="usr", schema={}, model="gemma:4", temperature=0.2)
    assert out["confidence"] == 0.5
    assert out["checklist"]["Q1"]["answer"] == "yes"


def test_client_raises_on_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    client = OllamaClient(base_url="http://test", transport=_stub_transport(handler))
    with pytest.raises(OllamaUnreachableError):
        client.chat(system="sys", user="usr", schema={}, model="gemma:4", temperature=0.2)


def test_client_raises_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = OllamaClient(base_url="http://test", transport=_stub_transport(handler))
    with pytest.raises(VerifierTimeoutError):
        client.chat(system="sys", user="usr", schema={}, model="gemma:4", temperature=0.2)


def test_client_raises_on_malformed_inner_json():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"message": {"content": "not json {{{"}}
        return httpx.Response(200, json=body)

    client = OllamaClient(base_url="http://test", transport=_stub_transport(handler))
    with pytest.raises(MalformedResponseError):
        client.chat(system="sys", user="usr", schema={}, model="gemma:4", temperature=0.2)


def test_client_sends_format_parameter():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        body = {
            "message": {
                "content": json.dumps(
                    {
                        "checklist": {q: {"answer": "yes", "cite": None} for q in ("Q1", "Q2", "Q3", "Q4", "Q5")},
                        "findings": {
                            "default_implementation": {"value": None, "cite": None},
                            "override_mechanism": {"value": None, "cite": None},
                            "abstraction_in_use": {"value": None, "cite": None},
                        },
                        "confidence": 0.5,
                        "evidence_summary": "ok",
                    }
                )
            }
        }
        return httpx.Response(200, json=body)

    client = OllamaClient(base_url="http://test", transport=_stub_transport(handler))
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    client.chat(system="sys", user="usr", schema=schema, model="gemma:4", temperature=0.2)
    assert captured["payload"]["format"] == schema
    assert captured["payload"]["model"] == "gemma:4"
    assert captured["payload"]["options"]["temperature"] == 0.2
    assert captured["payload"]["stream"] is False
