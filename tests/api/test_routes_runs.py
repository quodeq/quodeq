"""Tests for GET /api/projects/<project>/runs error handling."""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_project_runs_returns_json_500_on_a_read_failure(client, monkeypatch):
    """build_runs_unit raising OSError/sqlite3.Error/ValueError must yield a
    structured JSON 500, not a bare exception."""
    import quodeq.api.routes_runs as routes_mod

    monkeypatch.setattr(
        routes_mod, "build_runs_unit",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("index.db unreadable")),
    )

    resp = client.get("/api/projects/myproject/runs")

    assert resp.status_code == 500
    data = resp.get_json()
    assert data is not None
    assert data["code"] == "INTERNAL_ERROR"


def test_project_runs_propagates_an_error_outside_the_narrowed_tuple(client, monkeypatch):
    """A RuntimeError (not OSError/sqlite3.Error/ValueError) is a real bug in
    build_runs_unit, not a read failure, so it now escapes the route instead
    of being swallowed into a JSON 500."""
    import quodeq.api.routes_runs as routes_mod

    monkeypatch.setattr(
        routes_mod, "build_runs_unit",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected bug")),
    )

    with pytest.raises(RuntimeError):
        client.get("/api/projects/myproject/runs")
