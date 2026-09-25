"""The "no shared repository configured" answer keeps each route's own status."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from flask import Flask

from quodeq.api.routes_shared_common import no_shared_repo_error


@pytest.mark.parametrize("status", [HTTPStatus.CONFLICT, HTTPStatus.BAD_REQUEST])
def test_no_shared_repo_error_carries_the_given_status(status: HTTPStatus) -> None:
    with Flask(__name__).test_request_context():
        response, got = no_shared_repo_error(status)
        assert got == status
        assert response.get_json() == {"error": "no shared repository configured", "code": "NO_SHARED_REPO"}
