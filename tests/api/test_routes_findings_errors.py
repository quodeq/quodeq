"""Error-shape tests for the findings routes (usability finding 5950).

Sibling to test_routes_findings.py (611 lines, well past the 240-line
threshold for adding more) rather than an addition to it; the ``app``/
``client`` fixtures are imported from there.
"""
from __future__ import annotations

from tests.api.test_routes_findings import app, client  # noqa: F401 -- fixtures


def test_dismiss_unknown_project_returns_structured_404(client):
    """Finding 5950: the 404 for an unknown project must carry a machine-
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
