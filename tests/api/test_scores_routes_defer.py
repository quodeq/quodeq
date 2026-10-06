"""GET /api/projects/<project>/scores defers to the warm-up while it still owes the project."""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app

_PENDING_BODY = {"pending": True, "warmup": {"active": True, "projectsDone": 0, "projectsTotal": 2, "currentProjectName": "p"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_scores_answers_pending_while_the_warmup_owes_the_project(client, monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(
        "quodeq.api._scores_routes.defer_to_warmup",
        lambda reports_dir, project: asked.append(project) or _PENDING_BODY,
    )
    computed: list[str] = []
    monkeypatch.setattr("quodeq.api._scores_routes.get_project_scores", lambda *a, **kw: computed.append("x") or {})
    resp = client.get("/api/projects/demo/scores")
    assert resp.status_code == 202
    assert resp.get_json() == _PENDING_BODY
    assert asked == ["demo"]
    assert computed == []


def test_scores_builds_inline_when_nothing_is_owed(client, monkeypatch):
    monkeypatch.setattr("quodeq.api._scores_routes.defer_to_warmup", lambda reports_dir, project: None)
    monkeypatch.setattr("quodeq.api._scores_routes.get_project_scores", lambda *a, **kw: {"accumulated": {}, "trend": []})
    resp = client.get("/api/projects/demo/scores")
    assert resp.status_code == 200
