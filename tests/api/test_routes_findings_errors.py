"""Error-shape tests for the findings routes.

Sibling to test_routes_findings.py (611 lines, well past the 240-line
threshold for adding more) rather than an addition to it; the ``app``/
``client`` fixtures are imported from there.
"""
from __future__ import annotations

import pytest

from tests.api.test_routes_findings import app, client  # noqa: F401 -- fixtures


def test_dismiss_unknown_project_returns_structured_404(client):
    """The 404 for an unknown project must carry a machine-
    readable ``code`` like every other error branch in this file, instead
    of Flask's default abort() body.
    """
    resp = client.post("/api/findings/dismiss", json={
        "project": "does-not-exist",
        "req": "M-MOD-4", "file": "foo.js", "line": 4,
    })
    assert resp.status_code == 404
    body = resp.get_json()
    assert body is not None, "404 must be this file's JSON error shape, not Flask's default page"
    assert body["code"] == "NOT_FOUND"
    assert "error" in body


def test_restore_unknown_project_returns_structured_404(client):
    resp = client.post("/api/findings/restore", json={
        "project": "does-not-exist",
        "req": "M-MOD-4", "file": "foo.js", "line": 4,
    })
    assert resp.status_code == 404
    body = resp.get_json()
    assert body is not None
    assert body["code"] == "NOT_FOUND"


def test_unverify_unknown_project_returns_structured_404(client):
    resp = client.post("/api/findings/unverify", json={
        "project": "does-not-exist",
        "req": "M-MOD-4", "file": "foo.js", "line": 4,
    })
    assert resp.status_code == 404
    body = resp.get_json()
    assert body is not None
    assert body["code"] == "NOT_FOUND"


_FINDING = {"req": "M-MOD-4", "file": "foo.js", "line": 4}
_BAD_PROJECT_REQUESTS = [
    ("get", "/api/findings/dismissed?project=..%2Fetc", None),
    ("get", "/api/findings/verified?project=bad%00name", None),
    ("post", "/api/findings/dismiss", {"project": "../etc", **_FINDING}),
    ("post", "/api/findings/restore", {"project": "../etc", **_FINDING}),
    ("post", "/api/findings/unverify", {"project": "../etc", **_FINDING}),
    ("post", "/api/findings/restore-all", {"project": "../etc"}),
    ("post", "/api/findings/delete-all?confirm=true", {"project": "../etc"}),
    ("post", "/api/findings/delete", {
        "project": "../etc", "dimension": "maintainability", "principle": "p", "file": "foo.js",
    }),
]


@pytest.mark.parametrize(("method", "url", "body"), _BAD_PROJECT_REQUESTS)
def test_invalid_project_name_is_400(client, method, url, body):
    """A project name that is not a plain path segment is the client's
    error: a coded 400, never the catch-all 500."""
    resp = getattr(client, method)(url, json=body)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_INPUT"


def test_valid_unknown_project_is_still_404_or_empty(client):
    """A well-formed name with no directory keeps its answers: 404 for a
    mutation, an empty list for a listing."""
    resp = client.post("/api/findings/restore-all", json={"project": "does-not-exist"})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NOT_FOUND"
    listing = client.get("/api/findings/dismissed?project=does-not-exist")
    assert listing.status_code == 200
    assert listing.get_json() == []
