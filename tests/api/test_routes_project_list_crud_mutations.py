"""Tests for project delete, update-path, info and local-path creation validation."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)



class TestDeleteProject:
    def test_delete_requires_confirm(self, client):
        resp = client.delete("/api/projects/my-proj")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "CONFIRMATION_REQUIRED"

    def test_delete_success(self, client, provider):
        resp = client.delete("/api/projects/my-proj?confirm=true")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] == "my-proj"
        assert "my-proj" in provider.deleted

    def test_delete_not_found(self, client, provider):
        # First delete succeeds, second returns False
        provider.deleted.append("ghost")
        resp = client.delete("/api/projects/ghost?confirm=true")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"


class TestUpdateProjectPath:
    def test_requires_path(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_rejects_relative_path(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={"path": "relative/path"})
        assert resp.status_code == 400

    def test_rejects_path_traversal(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={"path": "/foo/../bar"})
        assert resp.status_code == 400

    def test_update_success(self, client, provider, tmp_path):
        # finding 5926: update_project_path now also requires the target to
        # be an existing directory, so a real one (not the placeholder
        # absolute path) is needed for the success path.
        target = tmp_path / "relocated"
        target.mkdir()
        resp = client.patch("/api/projects/my-proj/path", json={"path": str(target)})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["updated"] == "my-proj"
        assert body["path"] == str(target.resolve(strict=False))

    def test_update_not_found(self, client, provider, tmp_path):
        # Make update_project_path return False (project itself missing) --
        # the path must still be valid so the provider is actually reached.
        provider.update_project_path = lambda *a: False
        resp = client.patch("/api/projects/my-proj/path", json={"path": str(tmp_path)})
        assert resp.status_code == 404


class TestProjectInfo:
    def test_returns_info(self, client, provider):
        provider.project_info = {"name": "proj", "location": "local"}
        resp = client.get("/api/projects/proj/info")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "proj"

    def test_not_found(self, client, provider):
        provider.project_info = {}
        resp = client.get("/api/projects/proj/info")
        assert resp.status_code == 404


class TestCreateProjectLocalPathValidation:
    """SEC-24: the local-repo branch of create_project enforces the same
    allowlist as /api/scan (home or evaluations dir, no system paths)."""

    def test_local_repo_outside_home_rejected(self, client, tmp_path_factory):
        # Pin home to its own temp dir: the candidate repo must be outside it
        # on every platform (on Windows the pytest tmp root lives UNDER the
        # real home, so relying on the real Path.home() would pass the
        # allowlist and return 200).
        fake_home = tmp_path_factory.mktemp("fake-home")
        outside = tmp_path_factory.mktemp("outside-home-repo")
        with patch("pathlib.Path.home", return_value=fake_home):
            resp = client.post("/api/projects", json={"repo": str(outside)})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    @pytest.mark.skipif(
        os.name == "nt",
        reason="blocked paths are POSIX system dirs; /etc does not exist on "
        "Windows so the existence check 400s before the allowlist",
    )
    def test_local_repo_system_dir_rejected(self, client):
        # Widen home to "/" so the allowlist passes and the blocked-path
        # check is the branch under test.
        with patch("pathlib.Path.home", return_value=Path("/")):
            resp = client.post("/api/projects", json={"repo": "/etc"})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    def test_local_repo_under_evaluations_root_accepted(self, client, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        with patch(
            "quodeq.services.project_registration.register_project",
            return_value="uuid-1",
        ):
            resp = client.post("/api/projects", json={"repo": str(repo_dir)})
        assert resp.status_code == 200
        assert resp.get_json()["projectId"] == "uuid-1"

    def test_nonexistent_local_repo_still_400(self, client, tmp_path):
        resp = client.post(
            "/api/projects", json={"repo": str(tmp_path / "does-not-exist")}
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_REPO"
