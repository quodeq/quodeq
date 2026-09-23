"""Tests for project listing: pagination, hydration and warm-up wiring.

Split from test_routes_project_list.py. Shared fixtures
(_FakeProvider/provider/app/client) live in
tests/api/_routes_project_list_fixtures.py; delete/update-path/info/create
live in test_routes_project_list_crud_mutations.py.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.api.routes_project_list import register_project_list_routes
from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)


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

        from quodeq.services import fs_projects
        from quodeq.services.filesystem import FilesystemActionProvider

        for name in ["proj-a", "proj-b", "proj-c", "proj-d", "proj-e"]:
            proj = tmp_path / name
            proj.mkdir()
            (proj / "repository_info.json").write_text(json.dumps({
                "name": name, "path": str(tmp_path), "location": "local",
                "onboardingCompletedAt": "2026-01-01T00:00:00+00:00",
            }))

        calls: list[str] = []
        original = fs_projects.build_project_entry

        def _counting_build(reports_root, entry_name, runs, options, **kwargs):
            calls.append(entry_name)
            return original(reports_root, entry_name, runs, options, **kwargs)

        monkeypatch.setattr(fs_projects, "build_project_entry", _counting_build)

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


def test_list_projects_uses_injected_warmup_engine_not_the_singleton(monkeypatch):
    """C11: `warmup_engine` is an injected parameter, not a module-level
    singleton reference baked into the closure -- a caller-supplied engine
    must be the one the route actually calls."""
    from flask import Flask

    from quodeq.core.types import ProjectEntry
    from quodeq.services.warmup import WarmupEngine
    from tests.api._routes_project_list_fixtures import _FakeProvider

    fake_engine = WarmupEngine(warm_fn=lambda *_: None, list_fn=lambda _rd: [])
    enqueued = []
    monkeypatch.setattr(fake_engine, "enqueue", enqueued.append)
    monkeypatch.setattr(fake_engine, "snapshot", lambda: {"active": False, "projectsDone": 0, "projectsTotal": 0, "currentProjectName": None})

    # The real module-level singleton must NOT be touched by this request.
    singleton_enqueued = []
    monkeypatch.setattr("quodeq.api.routes_project_list.warmup_engine.enqueue", singleton_enqueued.append)

    provider = _FakeProvider()
    provider.projects = [ProjectEntry(id="a", name="a", summary_pending=True)]
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    with patch("quodeq.api.routes_project_list.reports_dir", return_value="/tmp"):
        register_project_list_routes(flask_app, provider, fake_engine)
        resp = flask_app.test_client().get("/api/projects")

    assert resp.status_code == 200
    assert resp.get_json()["warmup"]["active"] is False
    assert enqueued == ["a"]
    assert singleton_enqueued == []
