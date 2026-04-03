"""Tests for POST /api/projects/<id>/clone-local endpoint."""
from pathlib import Path
from unittest.mock import patch
import pytest
from quodeq.api.app import create_app

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(test_config={"TESTING": True})
    home = tmp_path.resolve()
    with app.test_client() as c:
        yield c, home


def _patch_home(home: Path):
    """Return a context manager that patches Path.home() to return *home*."""
    return patch("pathlib.Path.home", new=classmethod(lambda cls: home))


def test_clone_local_no_body_returns_400(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post("/api/projects/fake-uuid/clone-local", json={}, headers=_ORIGIN)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "destination" in data.get("error", "").lower()


def test_clone_local_outside_home_returns_403(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post(
            "/api/projects/fake-uuid/clone-local",
            json={"destination": "/etc"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 403
