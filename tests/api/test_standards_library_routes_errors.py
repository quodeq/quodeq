"""Post-PR review I4: library-backed standards routes keep their 502 contract.

Cluster 14 narrowed both routes from ``except Exception`` to
``(OSError, ValueError)``. That left two realistic transport failures falling
through to Flask's bare 500 instead of the documented ``{"error", "code"}``
502 body: ``http.client.HTTPException`` (``IncompleteRead``, ``BadStatusLine``,
...) is urllib's own family and NOT an ``OSError``, and a server answering with
valid JSON that is not an object used to ``AttributeError`` on ``data.get``.

Lives in its own module because ``test_standards_routes.py`` sits at the
300-line file cap; the fake client and app helper are imported from there.
"""
from __future__ import annotations

import http.client

from tests.api.test_standards_routes import (  # noqa: F401 -- `dirs` is a fixture
    _FakeLibraryHttpClient,
    _library_client,
    dirs,
)


def _import(c):
    return c.post(
        "/api/standards/library/import",
        json={"file": "standards/clean-arch.json"},
        headers={"Origin": "http://localhost"},
    )


def test_list_library_truncated_http_response_returns_502(dirs, monkeypatch):
    http_client = _FakeLibraryHttpClient(raise_exc=http.client.IncompleteRead(b"partial"))
    app = _library_client(dirs, monkeypatch, http_client)
    with app.test_client() as c:
        resp = c.get("/api/standards/library")
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "library_error"


def test_list_library_non_object_index_returns_502(dirs, monkeypatch):
    http_client = _FakeLibraryHttpClient({"https://example.com/index.json": ["not", "an", "object"]})
    app = _library_client(dirs, monkeypatch, http_client)
    with app.test_client() as c:
        resp = c.get("/api/standards/library")
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "library_error"


def test_import_from_library_truncated_http_response_returns_502(dirs, monkeypatch):
    http_client = _FakeLibraryHttpClient(raise_exc=http.client.IncompleteRead(b"partial"))
    app = _library_client(dirs, monkeypatch, http_client)
    with app.test_client() as c:
        resp = _import(c)
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "import_error"


def test_import_from_library_non_object_body_returns_502(dirs, monkeypatch):
    http_client = _FakeLibraryHttpClient({"https://example.com/standards/clean-arch.json": "just a string"})
    app = _library_client(dirs, monkeypatch, http_client)
    with app.test_client() as c:
        resp = _import(c)
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "import_error"
