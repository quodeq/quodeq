"""Tests for the findings dismiss/restore API endpoints."""
import json
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestDismissEndpoint:
    def test_dismiss_creates_entry(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
            "reason": "False positive",
        })
        assert resp.status_code == 200
        data = json.loads((project_dir / "dismissed.json").read_text())
        assert len(data) == 1
        assert data[0]["req"] == "M-MOD-4"

    def test_dismiss_missing_fields_returns_400(self, client):
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400


class TestRestoreEndpoint:
    def test_restore_removes_entry(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.post("/api/findings/restore", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
        })
        assert resp.status_code == 200
        assert not (project_dir / "dismissed.json").exists()


class TestListDismissedEndpoint:
    def test_list_returns_dismissed(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.get("/api/findings/dismissed?project=my-project")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1

    def test_list_empty_project(self, client):
        resp = client.get("/api/findings/dismissed?project=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json() == []
