"""Non-object JSON bodies answer 400 with a code; a missing body stays {}."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.helpers import optional_json_object_or_error


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


@pytest.mark.parametrize("raw", ["[1]", '"x"', "5", "true"])
def test_non_object_body_is_400_with_code(app: Flask, raw: str) -> None:
    with app.test_request_context(data=raw, content_type="application/json"):
        result = optional_json_object_or_error("INVALID_INPUT")
    assert isinstance(result, tuple)
    body, status = result
    assert status == 400
    assert body["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("raw", ["", "{not json"])
def test_missing_or_unparseable_body_is_empty_dict(app: Flask, raw: str) -> None:
    with app.test_request_context(data=raw, content_type="application/json"):
        assert optional_json_object_or_error() == {}


def test_object_body_passes_through(app: Flask) -> None:
    with app.test_request_context(data='{"a": 1}', content_type="application/json"):
        assert optional_json_object_or_error() == {"a": 1}


def test_force_reads_body_without_json_content_type(app: Flask) -> None:
    with app.test_request_context(data='{"a": 1}', content_type="text/plain"):
        assert optional_json_object_or_error(force=True) == {"a": 1}
        assert optional_json_object_or_error() == {}
