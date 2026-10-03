"""Request-body contract tests for the standards POST routes.

Final-review items 3, 4 and 6: a missing or non-string ``id`` on create, a
non-JSON or non-object body on any of the three POST handlers, and an import
ValueError raised after validation passed must all answer through this
module's ``{"error", "code"}`` shape with the right reason, never a 500 or a
misattributed "schema validation failed".

Sibling of test_standards_routes_errors.py; the ``dirs`` fixture and the
library-client helpers are reused from test_standards_routes.py.
"""
from __future__ import annotations

import json

import pytest

from quodeq.api.app import create_app

from tests.api.test_standards_routes import (  # noqa: F401 -- `dirs` is a fixture
    _FakeLibraryHttpClient,
    _library_client,
    dirs,
)

_ORIGIN = {"Origin": "http://localhost"}
_VALID_STANDARD = {
    "id": "ok-std", "name": "OK", "description": "",
    "weight": 1.0, "source": "", "principles": [],
}


def _app(dirs_):
    return create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(dirs_["evaluators"]),
        "STANDARDS_COMPILED_DIR": str(dirs_["compiled"]),
        "STANDARDS_DIMENSIONS_FILE": str(dirs_["dimensions"]),
    })


# --- item 3: create validates `id` up front ---------------------------------

def test_create_standard_without_id_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post("/api/standards", json={}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "id must be a non-empty string" in body["error"]


def test_create_standard_with_non_string_id_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post("/api/standards", json={"id": 5}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "id must be a non-empty string" in body["error"]


# --- item 4: the import handlers reject a non-JSON or non-object body -------

def test_import_standard_malformed_json_returns_structured_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/import", data="{not json",
            content_type="application/json", headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body is not None, "malformed JSON must still get the module's JSON error shape"
    assert body["code"] == "bad_request"
    assert "json" in body["error"].lower()


def test_import_standard_non_object_body_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/import", data="[]",
            content_type="application/json", headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"


def test_import_from_library_malformed_json_returns_structured_400(dirs, monkeypatch):
    app = _library_client(dirs, monkeypatch, _FakeLibraryHttpClient({}))
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/library/import", data="{not json",
            content_type="application/json", headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body is not None, "malformed JSON must still get the module's JSON error shape"
    assert body["code"] == "bad_request"
    assert "json" in body["error"].lower()


def test_import_from_library_non_object_body_returns_400(dirs, monkeypatch):
    app = _library_client(dirs, monkeypatch, _FakeLibraryHttpClient({}))
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/library/import", data="[]",
            content_type="application/json", headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"


# --- item 6: a ValueError raised after validation passed is not a schema error

class _RaisingService:
    """Stands in for StandardsService: import_from_file fails after the
    payload validated, the way scan_injection or a corrupt existing file
    would."""

    def import_from_file(self, data, force=False):
        raise ValueError("existing file is not valid json")


def test_import_standard_post_validation_value_error_is_not_reported_as_schema(dirs):
    app = _app(dirs)
    app._standards_service = _RaisingService()
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/import", json={"data": _VALID_STANDARD}, headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "schema validation failed" not in body["error"].lower(), (
        f"a non-validation ValueError must not be reported as a schema failure, "
        f"got: {body['error']!r}"
    )
    assert "not valid json" not in body["error"], "the exception text must not be echoed"
    assert body["code"] == "import_error"


def test_import_standard_validation_failure_still_lists_the_reasons(dirs):
    """The validation branch keeps the field-level reasons, now read off the
    typed error instead of re-running the validator in the except block."""
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/import", json={"data": {"name": "No ID"}}, headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "validation_error"
    lowered = body["error"].lower()
    assert "missing required field" in lowered
    assert "id" in lowered


def test_import_standard_still_imports_a_valid_payload(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/import", json={"data": _VALID_STANDARD}, headers=_ORIGIN,
        )
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "imported"
    stored = json.loads(dirs["evaluators"].joinpath("ok-std.json").read_text())
    assert stored["id"] == "ok-std"


# --- update/delete reject a traversal-shaped id with a coded 400 -----------

def test_update_standard_with_traversal_id_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.put(
            "/api/standards/a..b", json={"name": "x"}, headers=_ORIGIN,
        )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "bad_request"


def test_delete_standard_with_traversal_id_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.delete("/api/standards/a..b", headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "bad_request"


def test_update_standard_malformed_json_returns_json_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.put(
            "/api/standards/security", data="{bad",
            content_type="application/json", headers=_ORIGIN,
        )
    assert resp.status_code == 400
    assert resp.is_json


# --- duplicate rejects a non-string newId before touching the filesystem ---

@pytest.mark.parametrize("field", ["newId", "new_id"])
def test_duplicate_standard_with_non_string_new_id_returns_400(dirs, field):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/security/duplicate", json={field: ["a"]}, headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    # The bad newId must never reach the filesystem, e.g. as "['a'].json".
    assert list(dirs["evaluators"].iterdir()) == []
