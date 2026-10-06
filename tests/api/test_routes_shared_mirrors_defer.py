"""The shared Overview mirrors defer to the shared warm-up while it still owes the project.

Regression context: opening a cold shared project built its Overview inline
on the request path (the clone had no warm-up engine), which outlasted the
client's timeout and failed the Overview again on every retry. The mirrors
now queue the project and answer 202 pending, so the Overview shows one
loader and lands once the worker has warmed it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.services import shared_listing
from tests.api._routes_shared_read_fixtures import app, client  # noqa: F401 -- pytest fixtures

_PENDING_BODY = {"pending": True, "warmup": {"active": True, "projectsDone": 0, "projectsTotal": 1, "currentProjectName": "proj-a"}}


class _StubWarmup:
    def __init__(self, body):
        self.body = body
        self.asked: list[tuple[Path, str, str]] = []

    def defer(self, eval_root, url, project_id):
        self.asked.append((eval_root, url, project_id))
        return self.body


@pytest.mark.parametrize("path", ["dashboard", "accumulated", "scores"])
def test_mirror_answers_pending_while_the_shared_warmup_owes_the_project(client, shared_clone_fixture, monkeypatch, path):  # noqa: F811
    stub = _StubWarmup(_PENDING_BODY)
    monkeypatch.setattr(shared_listing, "shared_warmup", stub)
    built: list[str] = []
    monkeypatch.setattr("quodeq.api.routes_shared_mirrors.fs_reports.get_dashboard", lambda *a, **kw: built.append("x") or {})
    monkeypatch.setattr("quodeq.api.routes_shared_mirrors.fs_reports.get_accumulated", lambda *a, **kw: built.append("x") or {})
    monkeypatch.setattr("quodeq.api.routes_shared_mirrors.get_project_scores", lambda *a, **kw: built.append("x") or {})

    resp = client.get(f"/api/shared/projects/proj-a/{path}")

    assert resp.status_code == 202
    assert resp.get_json() == _PENDING_BODY
    assert [(url, pid) for _root, url, pid in stub.asked] == [(shared_clone_fixture, "proj-a")]
    assert built == []


@pytest.mark.parametrize("path", ["dashboard", "accumulated", "scores"])
def test_mirror_builds_inline_when_nothing_is_owed(client, shared_clone_fixture, monkeypatch, path):  # noqa: F811
    monkeypatch.setattr(shared_listing, "shared_warmup", _StubWarmup(None))
    resp = client.get(f"/api/shared/projects/proj-a/{path}")
    assert resp.status_code == 200


def test_mirror_rejects_an_invalid_name_before_asking_the_warmup(client, shared_clone_fixture, monkeypatch):  # noqa: F811
    stub = _StubWarmup(_PENDING_BODY)
    monkeypatch.setattr(shared_listing, "shared_warmup", stub)
    assert client.get("/api/shared/projects/..secret/dashboard").status_code == 400
    assert stub.asked == []
