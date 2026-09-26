"""api/_error_handlers.py: the app-wide fallback for an exception no route
handled.

Before this handler existed, an exception outside a route's own narrowed
catch tuple (see test_routes_runs.py, test_cluster4_scores_error.py, ...)
escaped all the way to Flask's default handling: a plain HTML 500 with no
machine-readable ``code``, unlike every other error response in this API.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app


class _StubProvider:
    def list_projects(self, reports_dir):
        return {"projects": []}


@pytest.fixture()
def client():
    app = create_app(provider=_StubProvider(), test_config={"TESTING": True})

    @app.get("/__test/boom")
    def _boom():
        raise RuntimeError("a secret detail that must never reach the client")

    with app.test_client() as c:
        yield c


def test_unhandled_exception_returns_coded_json_500(client):
    resp = client.get("/__test/boom")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body is not None, "Response body must be JSON, not a raw Flask error page"
    assert body["code"] == "INTERNAL_ERROR"


def test_unhandled_exception_message_never_echoes_the_exception_text(client):
    resp = client.get("/__test/boom")

    raw = resp.get_data(as_text=True)
    assert "a secret detail" not in raw
    assert "RuntimeError" not in raw
    assert "Traceback" not in raw


def test_a_404_is_unaffected_by_the_fallback_handler(client):
    resp = client.get("/__test/does-not-exist")

    assert resp.status_code == 404
