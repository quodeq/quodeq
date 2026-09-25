"""The route-response helpers every handler returns through: the jsonified
error pair, the JSON-body-or-response reader, the path-segment guard and the
dimension-eval response."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from flask import Flask

from quodeq.api.dimension_eval_wire import dimension_eval_response
from quodeq.api.helpers import (
    jsonify_error,
    optional_json_object_or_response,
    validate_segment,
)
from quodeq.core.types import EvalPending


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


def test_jsonify_error_turns_an_error_pair_into_a_response_pair(app: Flask) -> None:
    with app.test_request_context():
        response, status = jsonify_error(({"error": "nope", "code": "X"}, HTTPStatus.CONFLICT))
        assert status == HTTPStatus.CONFLICT
        assert response.get_json() == {"error": "nope", "code": "X"}


def test_optional_body_passes_an_object_through(app: Flask) -> None:
    with app.test_request_context(data='{"a": 1}', content_type="application/json"):
        assert optional_json_object_or_response("INVALID_INPUT") == {"a": 1}


def test_optional_body_is_empty_without_a_body(app: Flask) -> None:
    with app.test_request_context(data="", content_type="application/json"):
        assert optional_json_object_or_response("INVALID_INPUT") == {}


def test_optional_body_answers_a_non_object_with_a_coded_400(app: Flask) -> None:
    with app.test_request_context(data="[1]", content_type="application/json"):
        response, status = optional_json_object_or_response("INVALID_PARAM")
        assert status == HTTPStatus.BAD_REQUEST
        assert response.get_json() == {"error": "Request body must be a JSON object", "code": "INVALID_PARAM"}


def test_validate_segment_accepts_plain_segments(app: Flask) -> None:
    with app.test_request_context():
        assert validate_segment("proj", "run-1") is None


def test_validate_segment_answers_a_traversal_with_the_default_message(app: Flask) -> None:
    with app.test_request_context():
        response, status = validate_segment("proj", "..")
        assert status == HTTPStatus.BAD_REQUEST
        assert response.get_json() == {"error": "Invalid parameter", "code": "INVALID_INPUT"}


def test_validate_segment_uses_the_route_message(app: Flask) -> None:
    with app.test_request_context():
        response, status = validate_segment("../x", message="Invalid project name")
        assert status == HTTPStatus.BAD_REQUEST
        assert response.get_json() == {"error": "Invalid project name", "code": "INVALID_INPUT"}


def test_dimension_eval_response_is_404_without_a_payload(app: Flask) -> None:
    with app.test_request_context():
        response, status = dimension_eval_response(None)
        assert status == HTTPStatus.NOT_FOUND
        assert response.get_json() == {"error": "Eval file not found", "code": "NOT_FOUND"}


def test_dimension_eval_response_is_202_while_waiting(app: Flask) -> None:
    with app.test_request_context():
        response, status = dimension_eval_response({"waiting": True})
        assert status == HTTPStatus.ACCEPTED
        assert response.get_json() == {"waiting": True}


def test_dimension_eval_response_is_200_with_a_payload(app: Flask) -> None:
    with app.test_request_context():
        response = dimension_eval_response({"score": 7})
        assert response.status_code == HTTPStatus.OK
        assert response.get_json() == {"score": 7}


def test_dimension_eval_response_is_202_for_an_eval_pending(app: Flask) -> None:
    with app.test_request_context():
        response, status = dimension_eval_response(EvalPending(project="p", run_id="r", dimension="d"))
        assert status == HTTPStatus.ACCEPTED
        assert response.get_json() == {"waiting": True, "project": "p", "runId": "r", "dimension": "d"}
