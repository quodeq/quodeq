"""Tests for POST /api/browse/mkdir endpoint."""
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


def test_mkdir_creates_directory(app_client):
    c, home = app_client
    parent = home / "projects"
    parent.mkdir()
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(parent), "name": "new_folder"}, headers=_ORIGIN)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["created"] is True
    assert (parent / "new_folder").is_dir()


def test_mkdir_outside_home_returns_403(app_client):
    c, home = app_client
    outside = Path("/tmp")
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(outside), "name": "evil_dir"}, headers=_ORIGIN)
    assert resp.status_code == 403


def test_mkdir_path_traversal_in_name_returns_400(app_client):
    c, home = app_client
    parent = home / "projects"
    parent.mkdir()
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(parent), "name": "../escape"}, headers=_ORIGIN)
    assert resp.status_code == 400


def test_mkdir_missing_fields_returns_400(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(home)}, headers=_ORIGIN)
    assert resp.status_code == 400


def test_mkdir_conflict_returns_409(app_client):
    c, home = app_client
    parent = home / "projects"
    parent.mkdir()
    existing = parent / "already_there"
    existing.mkdir()
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(parent), "name": "already_there"}, headers=_ORIGIN)
    assert resp.status_code == 409


def test_mkdir_parent_not_found_returns_404(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post("/api/browse/mkdir", json={"path": str(home / "nonexistent"), "name": "child"}, headers=_ORIGIN)
    assert resp.status_code == 404
