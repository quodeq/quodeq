"""Tests for the findings restore-all, delete and delete-all API endpoints."""
from tests.api._routes_findings_fixtures import app, client  # noqa: F401 -- pytest fixtures


class TestRestoreAllEndpoint:
    def test_restore_all_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/restore-all", json={
            "project": "my-project", "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "restored" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "restore_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_restore_all_missing_project_returns_400(self, client):
        resp = client.post("/api/findings/restore-all", json={})
        assert resp.status_code == 400


class TestDeleteEndpoint:
    def test_delete_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/delete", json={
            "project": "my-project",
            "dimension": "security", "principle": "Integrity", "file": "a.py",
            "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "swept" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "delete"
        assert delta["runId"] == "run-1"
        assert delta["deleted"] == {
            "dimension": "security", "principle": "Integrity", "file": "a.py",
        }
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_delete_missing_fields_returns_400(self, client):
        resp = client.post("/api/findings/delete", json={"project": "x"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"


class TestDeleteAllEndpoint:
    def test_delete_all_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/delete-all?confirm=true", json={
            "project": "my-project", "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "deleted" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "delete_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_delete_all_missing_project_returns_400(self, client):
        resp = client.post("/api/findings/delete-all?confirm=true", json={})
        assert resp.status_code == 400

    def test_delete_all_without_confirm_returns_400(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/delete-all", json={"project": "my-project"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "CONFIRMATION_REQUIRED"

    def test_delete_all_with_confirm_true_deletes(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post(
            "/api/findings/delete-all?confirm=true", json={"project": "my-project"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
