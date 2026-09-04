"""Tests for project listing, mutation (delete/update-path), info, and creation.

Split from test_routes_project_list.py. Shared fixtures
(_FakeProvider/provider/app/client) live in
tests/api/_routes_project_list_fixtures.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.routes_project_list import register_project_list_routes
from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)

# Path.is_absolute() requires a drive letter on Windows ("/Users/test/code"
# is not absolute there), so use a platform-appropriate sample path for
# routes that validate absolute-ness.
_ABS_SAMPLE_PATH = "C:\\Users\\test\\code" if os.name == "nt" else "/Users/test/code"


class TestListProjects:
    def test_returns_empty_list(self, client, provider):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.get_json()["projects"] == []

    def test_returns_projects(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects")
        assert len(resp.get_json()["projects"]) == 3

    def test_pagination_offset(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?offset=1")
        data = resp.get_json()["projects"]
        assert len(data) == 2
        assert data[0]["name"] == "b"

    def test_pagination_limit(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?limit=2")
        data = resp.get_json()["projects"]
        assert len(data) == 2

    def test_pagination_offset_and_limit(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?offset=1&limit=1")
        data = resp.get_json()["projects"]
        assert len(data) == 1
        assert data[0]["name"] == "b"

    def test_pagination_hydrates_only_the_sliced_window(self, tmp_path, monkeypatch):
        """A5: pagination must not fully hydrate the whole project set.

        Wires the real FilesystemActionProvider (the fake provider above
        can't exercise hydration -- it just hands back pre-built objects)
        against 5 registered projects on disk, then asserts a 2-item page
        only triggers 2 calls to the expensive per-project hydration.
        """
        from flask import Flask

        from quodeq.services import _fs_projects
        from quodeq.services.filesystem import FilesystemActionProvider

        for name in ["proj-a", "proj-b", "proj-c", "proj-d", "proj-e"]:
            proj = tmp_path / name
            proj.mkdir()
            (proj / "repository_info.json").write_text(json.dumps({
                "name": name, "path": str(tmp_path), "location": "local",
                "onboardingCompletedAt": "2026-01-01T00:00:00+00:00",
            }))

        calls: list[str] = []
        original = _fs_projects._build_project_entry

        def _counting_build(reports_root, entry_name, runs, **kwargs):
            calls.append(entry_name)
            return original(reports_root, entry_name, runs, **kwargs)

        monkeypatch.setattr(_fs_projects, "_build_project_entry", _counting_build)

        flask_app = Flask(__name__)
        flask_app.config["TESTING"] = True
        provider = FilesystemActionProvider(reports_root=tmp_path)
        with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
            register_project_list_routes(flask_app, provider)
            resp = flask_app.test_client().get("/api/projects?offset=1&limit=2")

        assert resp.status_code == 200
        data = resp.get_json()["projects"]
        assert [p["name"] for p in data] == ["proj-b", "proj-c"]
        assert sorted(calls) == ["proj-b", "proj-c"], (
            f"expected hydration for only the sliced window, got {sorted(calls)}"
        )

    def test_pagination_preserves_auto_detected_parent(self, tmp_path):
        """Critical #1 regression (code review): a paginated page must carry
        the same auto-detected ``.parent`` an unpaginated listing computes.

        ``repository_info.json`` only ever gets an explicit "parent" field
        from the scope_path/subproject creation flow -- two independently
        registered local projects that merely share a path prefix rely
        entirely on ``_auto_detect_parents`` running at read time. The
        fixture below uses two *genuinely different* paths (one a real
        subdirectory of the other) so ``_find_best_parent``'s
        startswith-prefix check actually fires, unlike a fixture where every
        project shares one identical path.
        """
        from flask import Flask

        from quodeq.services.filesystem import FilesystemActionProvider

        (tmp_path / "parent-proj").mkdir()
        (tmp_path / "parent-proj" / "repository_info.json").write_text(json.dumps({
            "name": "parent-proj", "path": "/some/root/parent", "location": "local",
        }))
        (tmp_path / "child-proj").mkdir()
        (tmp_path / "child-proj" / "repository_info.json").write_text(json.dumps({
            "name": "child-proj", "path": "/some/root/parent/child", "location": "local",
        }))

        def _projects_by_name(query: str) -> dict:
            flask_app = Flask(__name__)
            flask_app.config["TESTING"] = True
            provider = FilesystemActionProvider(reports_root=tmp_path)
            with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
                register_project_list_routes(flask_app, provider)
                resp = flask_app.test_client().get(f"/api/projects{query}")
            return {p["name"]: p for p in resp.get_json()["projects"]}

        unpaginated = _projects_by_name("")
        paginated = _projects_by_name("?offset=0&limit=10")

        assert unpaginated["child-proj"]["parent"] == "parent-proj"
        assert paginated["child-proj"]["parent"] == "parent-proj", (
            "paginated hydration must propagate the index's auto-detected "
            "parent, not the raw (unenriched) repository_info.json value"
        )


def test_projects_response_carries_warmup_snapshot(app, provider, monkeypatch):
    from quodeq.core.types import ProjectEntry

    provider.projects = [ProjectEntry(id="a", name="a", summary_pending=True)]
    snap = {"active": True, "projectsDone": 1, "projectsTotal": 3, "currentProjectName": "a"}
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.snapshot", lambda: snap)
    enqueued = []
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.enqueue", enqueued.append)

    resp = app.test_client().get("/api/projects")

    assert resp.get_json()["warmup"] == snap
    assert resp.get_json()["projects"][0]["summaryPending"] is True
    assert enqueued == ["a"]


def test_projects_response_omits_warmup_when_engine_not_started(app, provider, monkeypatch):
    from quodeq.core.types import ProjectEntry

    provider.projects = [ProjectEntry(id="a", name="a")]
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.snapshot", lambda: None)

    resp = app.test_client().get("/api/projects")

    assert "warmup" not in resp.get_json()


def test_list_projects_only_warms_up_the_returned_page(app, provider, monkeypatch):
    from quodeq.core.types import ProjectEntry

    provider.projects = [
        ProjectEntry(id=f"p{i}", name=f"p{i}", summary_pending=True) for i in range(5)
    ]
    enqueued = []
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.enqueue", enqueued.append)
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.snapshot", lambda: None)

    client = app.test_client()
    resp = client.get("/api/projects?limit=2")

    assert resp.status_code == 200
    assert len(resp.get_json()["projects"]) == 2
    assert len(enqueued) == 2
    assert set(enqueued) == {"p0", "p1"}


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

    def test_update_success(self, client, provider):
        resp = client.patch("/api/projects/my-proj/path", json={"path": _ABS_SAMPLE_PATH})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["updated"] == "my-proj"
        assert body["path"] == str(Path(_ABS_SAMPLE_PATH).resolve(strict=False))

    def test_update_not_found(self, client, provider):
        # Make update_project_path return False
        provider.update_project_path = lambda *a: False
        resp = client.patch("/api/projects/my-proj/path", json={"path": _ABS_SAMPLE_PATH})
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
