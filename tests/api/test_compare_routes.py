"""Tests for GET /api/projects/<project>/compare-summary."""
from __future__ import annotations

import pytest

from quodeq.api import routes_compare
from quodeq.api.app import create_app


class _StubProvider:
    def list_projects(self, reports_dir):
        return {"projects": []}


@pytest.fixture()
def client():
    app = create_app(provider=_StubProvider())
    app.config["TESTING"] = True
    return app.test_client()


def test_returns_summary(client, monkeypatch):
    monkeypatch.setattr(
        routes_compare, "build_compare_summary",
        lambda root, project: {"project": project, "summary": {"numericAverage": 7.0}},
    )
    res = client.get("/api/projects/proj-a/compare-summary")
    assert res.status_code == 200
    assert res.get_json()["project"] == "proj-a"


def test_unknown_project_404(client, monkeypatch):
    monkeypatch.setattr(routes_compare, "build_compare_summary", lambda root, project: None)
    res = client.get("/api/projects/ghost/compare-summary")
    assert res.status_code == 404
    assert res.get_json()["code"] == "NOT_FOUND"


def test_invalid_segment_400(client):
    # validate_path_segment rejects traversal-looking ids before any
    # filesystem access happens.
    res = client.get("/api/projects/..%2F..%2Fetc/compare-summary")
    assert res.status_code in (400, 404)


def test_internal_error_500(client, monkeypatch):
    def boom(root, project):
        raise RuntimeError("kaput")

    monkeypatch.setattr(routes_compare, "build_compare_summary", boom)
    res = client.get("/api/projects/proj-a/compare-summary")
    assert res.status_code == 500
    assert res.get_json()["code"] == "INTERNAL_ERROR"
