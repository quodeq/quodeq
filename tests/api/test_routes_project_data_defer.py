"""The dashboard and accumulated routes defer to the warm-up while it still owes the project.

Regression context: at boot the Overview of a large project was built inline
on the request path while the warm-up rebuilt the same project beside it; the
build outlived the client's timeout and every retry started it again. The
routes now answer 202 with a pending body the client polls on, and build
inline only when the engine owes nothing for that project.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from quodeq.api.routes_project_data import register_project_data_routes

_PENDING_BODY = {"pending": True, "warmup": {"active": True, "projectsDone": 1, "projectsTotal": 3, "currentProjectName": "x"}}


@pytest.fixture
def client():
    app = Flask(__name__)
    provider = MagicMock()
    with patch("quodeq.api.routes_project_data.reports_dir", return_value="/tmp/reports"):
        register_project_data_routes(app, provider)
    app.config["TESTING"] = True
    with app.test_client() as c:
        c._provider = provider
        yield c


def test_dashboard_defers_to_the_warmup(client, monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(
        "quodeq.api.routes_project_data.defer_to_warmup",
        lambda reports_dir, project: asked.append(project) or _PENDING_BODY,
    )
    resp = client.get("/api/projects/myproj/dashboard?view=overview")
    assert resp.status_code == 202
    assert resp.get_json() == _PENDING_BODY
    assert asked == ["myproj"]
    client._provider.get_dashboard_overview.assert_not_called()
    client._provider.get_dashboard.assert_not_called()


def test_accumulated_defers_to_the_warmup(client, monkeypatch):
    monkeypatch.setattr("quodeq.api.routes_project_data.defer_to_warmup", lambda reports_dir, project: _PENDING_BODY)
    resp = client.get("/api/projects/myproj/accumulated")
    assert resp.status_code == 202
    assert resp.get_json() == _PENDING_BODY
    client._provider.get_accumulated.assert_not_called()


def test_routes_build_inline_when_nothing_is_owed(client, monkeypatch):
    monkeypatch.setattr("quodeq.api.routes_project_data.defer_to_warmup", lambda reports_dir, project: None)
    client._provider.get_dashboard.return_value = {"score": 85}
    client._provider.get_accumulated.return_value = {"dimensions": []}
    assert client.get("/api/projects/myproj/dashboard").status_code == 200
    assert client.get("/api/projects/myproj/accumulated").status_code == 200


def test_an_invalid_project_is_rejected_before_the_warmup_is_asked(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api.routes_project_data.defer_to_warmup",
        lambda reports_dir, project: pytest.fail("the warm-up must not see an invalid name"),
    )
    assert client.get("/api/projects/..secret/dashboard").status_code == 400
    assert client.get("/api/projects/..secret/accumulated").status_code == 400
