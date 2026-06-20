"""Finding #441 — /api/projects/<project>/scores route must return structured JSON 500.

When get_project_scores raises an unexpected exception the route previously
propagated it as a plain 500 with no JSON body. After the fix it must return
{"error": ..., "code": "INTERNAL_ERROR"} with status 500.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_project_scores_returns_json_500_on_unexpected_error(client, monkeypatch):
    """get_project_scores raising must yield a structured JSON 500, not a bare exception."""
    import quodeq.api._scores_routes as scores_mod

    monkeypatch.setattr(scores_mod, "get_project_scores", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("db exploded")))

    resp = client.get("/api/projects/myproject/scores")

    assert resp.status_code == 500
    data = resp.get_json()
    assert data is not None, "Response body must be JSON"
    assert "error" in data
    assert "code" in data
