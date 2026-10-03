"""Structured-error-contract tests for the standards routes.

Malformed JSON and validation-error bodies must go through this module's own
``error_response`` shape and surface the real reason, the CWE cache TTL
env var must be documented and validated, and ``limit``/``offset`` on
GET /api/standards must be validated rather than silently coerced.

Sibling to test_standards_routes.py (286 lines, at the file cap) rather
than an addition to it.
"""
from __future__ import annotations

import json
import logging

from quodeq.api.app import create_app
from quodeq.api.standards_read_routes import CweCache

from tests.api.test_standards_routes import (  # noqa: F401 -- `dirs` is a fixture
    _FakeLibraryHttpClient,
    _library_client,
    dirs,
)


def _app(dirs_):
    return create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(dirs_["evaluators"]),
        "STANDARDS_COMPILED_DIR": str(dirs_["compiled"]),
        "STANDARDS_DIMENSIONS_FILE": str(dirs_["dimensions"]),
    })


# --- 6332: malformed JSON body on POST /api/standards -----------------------

def test_create_standard_malformed_json_returns_structured_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards",
            data="{not valid json",
            content_type="application/json",
            headers={"Origin": "http://localhost"},
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body is not None, "malformed JSON must still get this module's JSON error shape"
    assert body["code"] == "bad_request"
    assert "json" in body["error"].lower()


# --- 6331: create's ValueError names the id and the real reason -------------
# (built from `payload`, never from `str(exc)` -- see test_no_exception_echo.py)

def test_create_standard_duplicate_id_reports_the_real_reason(dirs):
    app = _app(dirs)
    payload = {
        "id": "dup-std", "name": "Dup", "description": "",
        "weight": 1.0, "source": "", "principles": [],
    }
    with app.test_client() as c:
        c.post("/api/standards", json=payload, headers={"Origin": "http://localhost"})
        resp = c.post("/api/standards", json=payload, headers={"Origin": "http://localhost"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "dup-std" in body["error"]
    assert "already exists" in body["error"]


# --- 6144: library-import conflict states how to resolve it -----------------

def test_import_from_library_conflict_message_gives_a_resolution_path(dirs, monkeypatch):
    existing = {
        "id": "clean-arch", "name": "Clean Architecture", "description": "",
        "weight": 1.0, "source": "", "principles": [],
        "origin": "other-repo/clean-arch.json", "managed": False, "type": "custom",
    }
    dirs["evaluators"].joinpath("clean-arch.json").write_text(json.dumps(existing))
    remote_standard = {
        "id": "clean-arch", "name": "Clean Architecture", "description": "Test",
        "weight": 1.0, "source": "Martin", "principles": [],
    }
    http_client = _FakeLibraryHttpClient({"https://example.com/standards/clean-arch.json": remote_standard})
    app = _library_client(dirs, monkeypatch, http_client)
    with app.test_client() as c:
        resp = c.post(
            "/api/standards/library/import",
            json={"file": "standards/clean-arch.json"},
            headers={"Origin": "http://localhost"},
        )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "conflict"
    lowered = body["error"].lower()
    assert "duplicate" in lowered or "delete" in lowered, (
        f"conflict message must say how to resolve it, got: {body['error']!r}"
    )


# --- 6143: import_standard's ValueError names the real reason ---------------
# (built from `data`, never from `str(exc)` -- see test_no_exception_echo.py)

def test_import_standard_invalid_schema_reports_the_real_reason(dirs):
    app = _app(dirs)
    payload = {"data": {"name": "No ID"}}
    with app.test_client() as c:
        resp = c.post("/api/standards/import", json=payload, headers={"Origin": "http://localhost"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "validation_error"
    lowered = body["error"].lower()
    assert "missing required field" in lowered, (
        f"message must surface the real validation reason, got: {body['error']!r}"
    )
    assert "id" in lowered, "message must name which field failed"
    assert "principles" in lowered, "message must point at the fields import_from_file checks"


# --- 7283: QUODEQ_CWE_CACHE_TTL is documented and validated ------------------

def test_cwe_cache_ttl_env_non_numeric_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("QUODEQ_CWE_CACHE_TTL", "not-a-number")
    with caplog.at_level(logging.WARNING, logger="quodeq.api.standards_read_routes"):
        cache = CweCache()
    assert cache._ttl_s == 3600
    assert any("QUODEQ_CWE_CACHE_TTL" in r.getMessage() for r in caplog.records)


def test_cwe_cache_ttl_env_negative_falls_back_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("QUODEQ_CWE_CACHE_TTL", "-5")
    with caplog.at_level(logging.WARNING, logger="quodeq.api.standards_read_routes"):
        cache = CweCache()
    assert cache._ttl_s == 3600
    assert any("QUODEQ_CWE_CACHE_TTL" in r.getMessage() for r in caplog.records)


# --- 7287: limit/offset validation on GET /api/standards --------------------

def test_list_standards_absent_paging_uses_defaults(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.get("/api/standards")
    assert resp.status_code == 200


def test_list_standards_non_integer_limit_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.get("/api/standards?limit=abc")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "limit" in body["error"]


def test_list_standards_zero_limit_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.get("/api/standards?limit=0")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "limit" in body["error"]


def test_list_standards_negative_offset_returns_400(dirs):
    app = _app(dirs)
    with app.test_client() as c:
        resp = c.get("/api/standards?offset=-1")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "bad_request"
    assert "offset" in body["error"]
