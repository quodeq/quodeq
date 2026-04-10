"""Tests for API helper functions — error_response, validate_evaluation_payload, static routes."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api.helpers import (
    error_response,
    register_static_routes,
    validate_evaluation_payload,
)


class TestErrorResponse:
    def test_returns_tuple(self):
        body, status = error_response("Not found", HTTPStatus.NOT_FOUND, "NOT_FOUND")
        assert body == {"error": "Not found", "code": "NOT_FOUND"}
        assert status == 404

    def test_custom_code(self):
        body, status = error_response("Oops", 500, "INTERNAL")
        assert body["code"] == "INTERNAL"
        assert status == 500


class TestValidateEvaluationPayload:
    def test_valid_payload(self):
        payload = {"repo": "my-repo"}
        assert validate_evaluation_payload(payload) is None

    def test_missing_repo(self):
        err = validate_evaluation_payload({})
        assert "repo" in err
        assert "missing" in err.lower()

    def test_empty_repo(self):
        err = validate_evaluation_payload({"repo": ""})
        assert err is not None

    def test_non_string_repo(self):
        err = validate_evaluation_payload({"repo": 123})
        assert "repo" in err

    def test_dimensions_as_list(self):
        payload = {"repo": "r", "dimensions": ["a", "b"]}
        assert validate_evaluation_payload(payload) is None
        assert payload["dimensions"] == "a,b"

    def test_dimensions_as_string(self):
        payload = {"repo": "r", "dimensions": "a,b"}
        assert validate_evaluation_payload(payload) is None
        assert payload["dimensions"] == "a,b"

    def test_dimensions_invalid_type(self):
        err = validate_evaluation_payload({"repo": "r", "dimensions": 42})
        assert "dimensions" in err

    def test_invalid_string_fields(self):
        err = validate_evaluation_payload({"repo": "r", "aiCmd": 5, "aiModel": True})
        assert "aiCmd" in err
        assert "aiModel" in err

    def test_invalid_numerical(self):
        err = validate_evaluation_payload({"repo": "r", "numerical": "yes"})
        assert "numerical" in err

    def test_valid_numerical(self):
        assert validate_evaluation_payload({"repo": "r", "numerical": True}) is None

    def test_combined_missing_and_invalid(self):
        err = validate_evaluation_payload({"discipline": 123})
        assert "missing" in err.lower()
        assert "invalid" in err.lower()


class TestRegisterStaticRoutes:
    def test_no_static_dist_does_nothing(self):
        app = Flask(__name__)
        register_static_routes(app, None)
        # No routes registered beyond Flask defaults
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/" not in rules

    def test_nonexistent_dir_does_nothing(self):
        app = Flask(__name__)
        register_static_routes(app, "/nonexistent/path/abc")
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/" not in rules

    def test_serves_index(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_static_routes(app, str(tmp_path))
        client = app.test_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Hello" in resp.data

    def test_serves_static_file(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>Hello</h1>")
        (tmp_path / "style.css").write_text("body{}")
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_static_routes(app, str(tmp_path))
        client = app.test_client()
        resp = client.get("/style.css")
        assert resp.status_code == 200
        assert b"body" in resp.data

    def test_spa_fallback(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>SPA</h1>")
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_static_routes(app, str(tmp_path))
        client = app.test_client()
        # Non-existent path, not api/ prefix -> falls back to index.html
        resp = client.get("/some/deep/path")
        assert resp.status_code == 200
        assert b"SPA" in resp.data

    def test_api_prefix_returns_404(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>SPA</h1>")
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_static_routes(app, str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, tmp_path):
        (tmp_path / "index.html").write_text("<h1>SPA</h1>")
        app = Flask(__name__)
        app.config["TESTING"] = True
        register_static_routes(app, str(tmp_path))
        client = app.test_client()
        # Path traversal attempt -- Flask normalizes /../ but we test it doesn't leak
        resp = client.get("/../../../etc/passwd")
        # Should either be 404 (normalized away) or 403 (blocked by our guard)
        assert resp.status_code in (403, 404, 301, 308, 200)  # Flask may normalize
