"""Tests for POST /api/shared/projects/<project>/pull.

Pulls a project from the shared clone into the local evaluations directory
by building an in-memory zip of the clone's project directory
(``_build_project_zip``) and feeding it to ``import_zip_stream`` -- the same
hardened validation/collision logic used by the manual
``POST /api/projects/import`` route (see tests/api/test_project_import.py).

Note on project naming: real local project directories under reports_dir are
named by UUID (``import_project.py``'s ``_validate_archive`` requires the
zip's single top-level directory to be a valid UUID), and ``publish_project``
mirrors the source directory name as-is into the shared repo -- so a
realistic pull target is UUID-named too. This intentionally differs from
``tests/api/test_routes_shared_read.py``'s ``shared_clone_fixture``, which
publishes under the human-friendly slug ``"proj-a"`` purely for readability
across its read-endpoint tests; that slug is not a valid zip top-level
directory name for ``import_zip_stream`` (it fails the UUID check with
``BAD_LAYOUT``), so these pull tests use their own UUID-named fixture to
exercise the real success and collision paths.
"""
from __future__ import annotations

import json
import subprocess
import uuid as _uuid
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services.shared_publish import publish_project
from quodeq.services.shared_settings import SharedSettings, write_settings

_ORIGIN = {"Origin": "http://localhost"}


def _make_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


@pytest.fixture()
def app():
    return create_app(test_config={"TESTING": True})


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def local_eval_dir(tmp_path, monkeypatch) -> Path:
    """The LOCAL evaluations directory the pull route writes into."""
    d = tmp_path / "local-evaluations"
    d.mkdir()
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(d))
    return d


@pytest.fixture()
def shared_clone_fixture(tmp_path, monkeypatch):
    """A real published shared-repo clone containing one UUID-named project.

    Follows the same bare-origin + publish_project recipe as
    tests/services/test_shared_repo.py and
    tests/api/test_routes_shared_read.py, but publishes a UUID-named project
    (see module docstring) with a complete repository_info.json so the
    import-side validation (_validate_repository_info requires 'name' and
    'path') succeeds.

    Returns (url, project_uuid).
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")

    url = _make_origin(tmp_path)
    publish_source = tmp_path / "publish-source"
    project_uuid = str(_uuid.uuid4())
    project_dir = publish_source / project_uuid
    project_dir.mkdir(parents=True)
    (project_dir / "repository_info.json").write_text(
        json.dumps({
            "uuid": project_uuid,
            "name": "proj-a",
            "location": "local",
            "path": "/tmp/proj-a",
        }),
        encoding="utf-8",
    )
    # build_project_list() (backing GET /api/projects) skips any project dir
    # with zero runs, so give it one minimal run -- list_runs only requires
    # evidence/manifest.json to exist to count a run directory as a run.
    run_dir = project_dir / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "status.json").write_text(
        json.dumps({"state": "done", "schema_version": 2}), encoding="utf-8",
    )

    publish_project(project_uuid, url, evaluations_root=publish_source)
    write_settings(SharedSettings(url=url))
    return url, project_uuid


@pytest.fixture()
def local_eval_dir_with_collision(local_eval_dir, shared_clone_fixture) -> Path:
    """local_eval_dir, pre-seeded with a project at the same UUID the shared
    clone publishes -- forces the same-uuid 409 collision path."""
    _, project_uuid = shared_clone_fixture
    existing = local_eval_dir / project_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(
        json.dumps({
            "uuid": project_uuid,
            "name": "existing-local-name",
            "location": "local",
            "path": "/tmp/existing",
        }),
        encoding="utf-8",
    )
    return local_eval_dir


def _pull(client, project: str, action: str | None = None):
    body = {"action": action} if action is not None else {}
    return client.post(
        f"/api/shared/projects/{project}/pull",
        json=body,
        headers=_ORIGIN,
    )


# --- happy path ---------------------------------------------------------------

def test_pull_materializes_local_copy(client, shared_clone_fixture, local_eval_dir):
    _, project_uuid = shared_clone_fixture
    resp = _pull(client, project_uuid)
    assert resp.status_code in (200, 201), resp.get_json()
    assert (local_eval_dir / project_uuid / "repository_info.json").exists()

    listing = client.get("/api/projects").get_json()
    ids = [p.get("id") or p.get("name") for p in listing["projects"]]
    assert any(project_uuid in str(i) for i in ids)


# --- collision handling --------------------------------------------------------

def test_pull_collision_returns_409(client, shared_clone_fixture, local_eval_dir_with_collision):
    _, project_uuid = shared_clone_fixture
    resp = _pull(client, project_uuid)
    assert resp.status_code == 409  # caller retries with {"action": "copy"}
    body = resp.get_json()
    assert body["code"] == "PROJECT_EXISTS"
    assert body["kind"] == "same_uuid"


def test_pull_collision_replace_overwrites(client, shared_clone_fixture, local_eval_dir_with_collision):
    _, project_uuid = shared_clone_fixture
    existing = local_eval_dir_with_collision / project_uuid
    (existing / "old-marker.txt").write_text("stale", encoding="utf-8")

    resp = _pull(client, project_uuid, action="replace")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == project_uuid
    assert body["renamed"] is False
    assert not (existing / "old-marker.txt").exists()
    info = json.loads((existing / "repository_info.json").read_text())
    assert info["name"] == "proj-a"


def test_pull_collision_copy_creates_new_uuid(client, shared_clone_fixture, local_eval_dir_with_collision):
    _, project_uuid = shared_clone_fixture
    resp = _pull(client, project_uuid, action="copy")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] != project_uuid
    assert body["sourceProjectId"] == project_uuid
    assert body["renamed"] is True
    # Both the pre-existing local project and the newly copied one exist.
    assert (local_eval_dir_with_collision / project_uuid).exists()
    assert (local_eval_dir_with_collision / body["projectId"]).exists()


def test_pull_invalid_action_returns_400(client, shared_clone_fixture, local_eval_dir):
    _, project_uuid = shared_clone_fixture
    resp = _pull(client, project_uuid, action="nuke")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_ACTION"


def test_pull_non_string_action_returns_400(client, shared_clone_fixture, local_eval_dir):
    _, project_uuid = shared_clone_fixture
    resp = client.post(
        f"/api/shared/projects/{project_uuid}/pull",
        json={"action": ["copy"]},
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_ACTION"


# --- not-found / validation ------------------------------------------------

def test_pull_project_not_found_in_shared_repo_returns_404(client, shared_clone_fixture, local_eval_dir):
    resp = _pull(client, "does-not-exist")
    assert resp.status_code == 404


def test_pull_invalid_project_segment_returns_400(client, shared_clone_fixture, local_eval_dir):
    resp = client.post(
        "/api/shared/projects/%2e%2e/pull",
        json={},
        headers=_ORIGIN,
    )
    assert resp.status_code == 400


def test_pull_without_body_defaults_to_no_action(client, shared_clone_fixture, local_eval_dir):
    """A POST with no JSON body at all (not even {}) must not 400/500."""
    _, project_uuid = shared_clone_fixture
    resp = client.post(f"/api/shared/projects/{project_uuid}/pull", headers=_ORIGIN)
    assert resp.status_code in (200, 201), resp.get_json()
