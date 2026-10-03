"""Tests for POST /api/projects with cloneDest / ephemeral support (Task A3)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.services.github_access import AccessMethod, AccessResult
from quodeq.shared.git_errors import GitFailureKind

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    evaluations_dir = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evaluations_dir))
    app = create_app(test_config={"TESTING": True})
    home = tmp_path.resolve()
    with app.test_client() as c, patch(
        "pathlib.Path.home", new=classmethod(lambda cls: home)
    ):
        yield c


def test_post_projects_url_requires_clone_dest_or_ephemeral(client):
    resp = client.post(
        "/api/projects", json={"repo": "https://github.com/x/y.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "MISSING_CLONE_DEST"


def test_post_projects_url_with_clone_dest_returns_real_scan(client, tmp_path):
    # cloneDest must be under home (the fixture sets home to tmp_path).
    parent = tmp_path / "code"
    parent.mkdir()

    def fake_register(reports_dir, spec, **kw):
        uuid = "test-uuid"
        d = Path(reports_dir) / uuid
        d.mkdir(parents=True, exist_ok=True)
        (d / "scan.json").write_text(json.dumps({"total_files": 5, "code_files": 5}))
        (d / "repository_info.json").write_text(json.dumps({
            "location": "local", "path": str(parent / "y"),
        }))
        return uuid

    with patch(
        "quodeq.services.project_registration.register_project", side_effect=fake_register
    ):
        resp = client.post(
            "/api/projects",
            json={
                "repo": "https://github.com/x/y.git",
                "cloneDest": str(parent),
            },
            headers=_ORIGIN,
        )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == "test-uuid"
    assert body["scanData"]["total_files"] == 5


def test_post_projects_url_ephemeral_skips_clone_dest(client, tmp_path):
    def fake_register(reports_dir, spec, **kw):
        assert spec.ephemeral is True
        assert spec.clone_dest is None
        uuid = "ephemeral-uuid"
        d = Path(reports_dir) / uuid
        d.mkdir(parents=True, exist_ok=True)
        (d / "scan.json").write_text(json.dumps({"total_files": 3}))
        (d / "repository_info.json").write_text(json.dumps({
            "location": "local", "ephemeral": True,
        }))
        return uuid

    with patch(
        "quodeq.services.project_registration.register_project", side_effect=fake_register
    ):
        resp = client.post(
            "/api/projects",
            json={
                "repo": "https://github.com/x/y.git",
                "ephemeral": True,
            },
            headers=_ORIGIN,
        )
    assert resp.status_code == 200, resp.get_json()


def test_post_projects_rejects_metadata_endpoint_ssrf(client):
    """SSRF: POST /api/projects pointed at a cloud metadata endpoint is rejected
    with 400 and never reaches git clone."""
    clone_calls = []
    with patch(
        "quodeq.services._project_registration_steps.run_git_clone",
        side_effect=lambda url, dest: clone_calls.append(url),
    ):
        resp = client.post(
            "/api/projects",
            json={"repo": "https://169.254.169.254/latest/meta-data", "ephemeral": True},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "INVALID_URL"  # the access ladder's URL guard answers first
    assert clone_calls == [], "SSRF: git clone must never run for a metadata-endpoint URL"


def test_post_projects_clone_dest_under_home_is_created_when_missing(client, tmp_path):
    """A missing folder under home is created rather than refused: the wizard's
    default destination (~/quodeq/repos) does not exist on a fresh machine."""
    missing = tmp_path / "quodeq" / "repos"
    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(missing),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code != 400 or resp.get_json()["code"] != "INVALID_CLONE_DEST", resp.get_json()
    assert missing.is_dir()


def test_post_projects_clone_dest_tilde_means_home(client, tmp_path):
    """The wizard sends "~/quodeq/repos"; the server expands the tilde to the home folder."""
    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": "~/quodeq/repos",
        },
        headers=_ORIGIN,
    )
    assert resp.status_code != 400 or resp.get_json()["code"] != "INVALID_CLONE_DEST", resp.get_json()
    assert (tmp_path / "quodeq" / "repos").is_dir()


def test_post_projects_clone_dest_must_be_directory_not_file(client, tmp_path):
    """If cloneDest points to a file (not a directory), reject with INVALID_CLONE_DEST."""
    # Fixture sets home to tmp_path, so a file under tmp_path is "under home" but not a dir.
    a_file = tmp_path / "regular-file.txt"
    a_file.write_text("not a directory")

    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(a_file),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_CLONE_DEST"


def test_post_projects_clone_dest_must_be_under_home(client, tmp_path):
    """If cloneDest resolves outside the user's home folder, reject with INVALID_CLONE_DEST."""
    # Fixture pins home to tmp_path. Build a sibling path that exists but is outside home.
    outside = tmp_path.parent / "outside-home-dir"
    outside.mkdir(exist_ok=True)

    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(outside),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_CLONE_DEST"


def test_post_projects_local_repo_path_must_be_directory_not_file(client, tmp_path):
    """A local repo path pointing at a FILE is rejected with a message that
    says so (a real registration once slipped through as .../lib/player.js
    and 404'd forever after)."""
    a_file = tmp_path / "player.js"
    a_file.write_text("// not a repo")

    resp = client.post(
        "/api/projects",
        json={"repo": str(a_file)},
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_REPO"
    assert "file, not a directory" in body["error"]


def _capture_spec(specs):
    def fake_register(reports_dir, spec, **kw):
        specs.append(spec)
        d = Path(reports_dir) / "u1"
        d.mkdir(parents=True, exist_ok=True)
        (d / "scan.json").write_text(json.dumps({"total_files": 1}))
        (d / "repository_info.json").write_text(json.dumps({"location": "local", "ephemeral": True}))
        return "u1"
    return fake_register


def test_create_project_url_probes_first_and_threads_env(client, monkeypatch):
    env = {"GIT_CONFIG_COUNT": "1"}
    reachable = AccessResult(True, AccessMethod.GH, GitFailureKind.OK, "", "github.com", True, env, "https://github.com/o/r.git")
    monkeypatch.setattr("quodeq.api.routes_project_create.resolve_access", lambda url: reachable)
    specs = []
    with patch("quodeq.services.project_registration.register_project", side_effect=_capture_spec(specs)):
        client.post("/api/projects", json={"repo": "git@github.com:o/r.git", "ephemeral": True}, headers=_ORIGIN)
    assert specs[0].git_env == env
    assert specs[0].clone_url == "https://github.com/o/r.git"
    assert specs[0].repo == "git@github.com:o/r.git"


def test_create_project_url_probe_failure_is_400(client, monkeypatch):
    unreachable = AccessResult(False, AccessMethod.NONE, GitFailureKind.NOT_FOUND, "nope", "github.com", True, None)
    monkeypatch.setattr("quodeq.api.routes_project_create.resolve_access", lambda url: unreachable)
    specs = []
    with patch("quodeq.services.project_registration.register_project", side_effect=_capture_spec(specs)):
        resp = client.post("/api/projects", json={"repo": "https://github.com/o/r.git", "ephemeral": True}, headers=_ORIGIN)
    assert resp.status_code == 400 and resp.get_json()["code"] == "ACCESS_NOT_FOUND"
    assert specs == []


def test_create_project_local_path_never_probes(client, monkeypatch, tmp_path):
    monkeypatch.setattr("quodeq.api.routes_project_create.resolve_access", lambda url: pytest.fail("probed a local path"))
    repo = tmp_path / "proj"
    repo.mkdir()
    client.post("/api/projects", json={"repo": str(repo)}, headers=_ORIGIN)


def test_create_project_clone_failure_forgets_the_cached_method(client, monkeypatch):
    from quodeq.services.base import CreateProjectResult, CreateProjectStatus
    forgotten = []
    monkeypatch.setattr("quodeq.api.routes_project_create.forget_url", forgotten.append)
    result = CreateProjectResult(status=CreateProjectStatus.CLONE_FAILED, message="x", clone_error_kind=GitFailureKind.UNKNOWN)
    with patch("quodeq.services.filesystem.FilesystemActionProvider.create_project", return_value=result):
        client.post("/api/projects", json={"repo": "https://github.com/o/r.git", "ephemeral": True}, headers=_ORIGIN)
    assert forgotten == ["https://github.com/o/r.git"]
