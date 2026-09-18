"""Malformed paging parameters answer 400 on every paginated route.

Final-review item 10: GET /api/standards validated ``limit``/``offset`` by
hand while list_projects, both findings lists and the evaluations list kept
``request.args.get(..., type=int)``, which silently substituted the default
for a malformed value. One helper now holds the rule for all of them
(quodeq.api.helpers.page_params); the two shared findings mirrors are covered
in test_routes_shared_read.py, next to their clone fixture.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes
from quodeq.api.routes_project_list import register_project_list_routes
from tests.api._routes_project_list_fixtures import _FakeProvider
from tests.api.test_action_api import StubProvider


def _assert_named_400(resp, name: str) -> None:
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert name in body["error"], f"the message must name the parameter, got {body['error']!r}"


def _findings_client(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(app)
    return app.test_client()


@pytest.fixture()
def evaluations_client(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    from quodeq.api.app import create_app

    class _ListProvider(StubProvider):
        def list_evaluations(self, *, limit: int = 0, reports_dir=None, states=None):
            return []

    return create_app(_ListProvider()).test_client()


# --- GET /api/projects ------------------------------------------------------

def test_list_projects_rejects_a_malformed_limit(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
        register_project_list_routes(app, _FakeProvider())
        resp = app.test_client().get("/api/projects?limit=abc")
    _assert_named_400(resp, "limit")


def test_list_projects_without_paging_still_lists(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
        register_project_list_routes(app, _FakeProvider())
        resp = app.test_client().get("/api/projects")
    assert resp.status_code == 200
    assert resp.get_json()["projects"] == []


def test_list_projects_accepts_limit_zero_as_no_limit(tmp_path):
    """limit=0 is this route's "no limit" sentinel, not an out-of-range value."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
        register_project_list_routes(app, _FakeProvider())
        resp = app.test_client().get("/api/projects?limit=0")
    assert resp.status_code == 200


# --- GET /api/findings/dismissed and /api/findings/verified -----------------

def test_list_dismissed_rejects_a_malformed_limit(tmp_path):
    resp = _findings_client(tmp_path).get("/api/findings/dismissed?project=p&limit=abc")
    _assert_named_400(resp, "limit")


def test_list_dismissed_rejects_a_negative_offset(tmp_path):
    resp = _findings_client(tmp_path).get("/api/findings/dismissed?project=p&offset=-1")
    _assert_named_400(resp, "offset")


def test_list_verified_rejects_a_malformed_limit(tmp_path):
    resp = _findings_client(tmp_path).get("/api/findings/verified?project=p&limit=abc")
    _assert_named_400(resp, "limit")


def test_findings_lists_still_clamp_an_oversized_limit(tmp_path):
    """The hard cap stays a clamp, not a 400: the UI asks for 5000."""
    client = _findings_client(tmp_path)
    assert client.get("/api/findings/dismissed?project=p&limit=99999").status_code == 200
    assert client.get("/api/findings/verified?project=p&limit=99999").status_code == 200


# --- GET /api/evaluations --------------------------------------------------

def test_list_evaluations_rejects_a_malformed_limit(evaluations_client):
    _assert_named_400(evaluations_client.get("/api/evaluations?limit=abc"), "limit")


def test_list_evaluations_without_a_limit_still_lists(evaluations_client):
    resp = evaluations_client.get("/api/evaluations")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_evaluations_accepts_limit_zero_as_no_limit(evaluations_client):
    assert evaluations_client.get("/api/evaluations?limit=0").status_code == 200
