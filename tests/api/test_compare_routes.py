"""Tests for GET /api/projects/<project>/compare-summary and GET /api/fleet/compare."""
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
    # OSError, not an arbitrary Exception: the route's except was narrowed to
    # (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) (R-FT-7),
    # the realistic surface of build_compare_summary's cache/sqlite/git reads.
    def boom(root, project):
        raise OSError("kaput")

    monkeypatch.setattr(routes_compare, "build_compare_summary", boom)
    res = client.get("/api/projects/proj-a/compare-summary")
    assert res.status_code == 500
    assert res.get_json()["code"] == "INTERNAL_ERROR"


def test_fleet_returns_summaries_and_errors(client, monkeypatch):
    seen = {}

    def fake_fleet(root, names, **_kw):
        seen["names"] = names
        return {"summaries": [{"project": n} for n in names[:1]], "errors": {names[1]: "Project not found"}}

    monkeypatch.setattr(routes_compare, "build_fleet_compare", fake_fleet)
    res = client.get("/api/fleet/compare?projects=proj-a,%20ghost%20,,")
    assert res.status_code == 200
    assert seen["names"] == ["proj-a", "ghost"]
    assert res.get_json() == {"summaries": [{"project": "proj-a"}], "errors": {"ghost": "Project not found"}}


def test_fleet_without_projects_400(client):
    res = client.get("/api/fleet/compare")
    assert res.status_code == 400
    assert res.get_json()["code"] == "INVALID_INPUT"
    assert client.get("/api/fleet/compare?projects=,%20,").status_code == 400


def test_fleet_rejects_a_bad_segment_before_any_read(client, monkeypatch):
    def boom(root, names):
        raise AssertionError("must not build with an invalid name")

    monkeypatch.setattr(routes_compare, "build_fleet_compare", boom)
    res = client.get("/api/fleet/compare?projects=proj-a,..%2Fetc")
    assert res.status_code == 400
    assert res.get_json()["error"] == "Invalid project name"
