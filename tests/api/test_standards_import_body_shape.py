"""Both standards import routes reject a JSON body that is not an object.

A JSON array parses fine but has no ``.get``; before the guard both routes
raised AttributeError (a bare 500) instead of the module's ``{"error",
"code"}`` 400 body.

Fixtures and the fake library client come from ``test_standards_routes.py``,
which sits at the 300-line file cap.
"""
from __future__ import annotations

from tests.api.test_standards_routes import (  # noqa: F401 -- `client`/`dirs` are fixtures
    _FakeLibraryHttpClient,
    _library_client,
    client,
    dirs,
)

_ORIGIN = {"Origin": "http://localhost"}


def test_import_standard_list_body_returns_400(client):
    resp = client.post("/api/standards/import", json=[{"data": {}}], headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "object" in body["error"]


def test_import_from_library_list_body_returns_400(dirs, monkeypatch):
    app = _library_client(dirs, monkeypatch, _FakeLibraryHttpClient())
    with app.test_client() as c:
        resp = c.post("/api/standards/library/import", json=["standards/x.json"], headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "object" in body["error"]


def test_import_from_library_non_string_file_returns_400(dirs, monkeypatch):
    """``{"file": 5}`` passes the truthiness check; before the type guard the
    ``".." in file_path`` test then raised TypeError, a bare 500."""
    app = _library_client(dirs, monkeypatch, _FakeLibraryHttpClient())
    with app.test_client() as c:
        resp = c.post("/api/standards/library/import", json={"file": 5}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "file" in body["error"] and "string" in body["error"]
