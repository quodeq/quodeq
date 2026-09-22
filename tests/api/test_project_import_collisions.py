"""Tests for POST /api/projects/import: same-uuid and same-identity collision resolution."""
from __future__ import annotations

import json
import uuid

from tests.api._project_import_fixtures import (  # noqa: F401 -- app_client is a pytest fixture
    _make_zip,
    _patch_home,
    _post_zip,
    app_client,
)


def test_import_same_uuid_collision_returns_409(app_client):
    c, home, eval_dir = app_client
    project_uuid = str(uuid.uuid4())
    # Pre-create the project directory with valid repository_info.json
    existing = eval_dir / project_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": project_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    data = _make_zip(project_uuid=project_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["kind"] == "same_uuid"
    assert body["existingProjectId"] == project_uuid
    assert body["projectName"] == "myrepo"


def test_import_same_uuid_replace_overwrites(app_client):
    c, home, eval_dir = app_client
    project_uuid = str(uuid.uuid4())
    existing = eval_dir / project_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": project_uuid, "name": "old-name", "location": "local", "path": "/tmp/old",
    }))
    (existing / "old-marker.txt").write_text("old content")
    data = _make_zip(project_uuid=project_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data, action="replace")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == project_uuid
    assert body["renamed"] is False
    # Old marker is gone, new repository_info.json reflects imported name
    assert not (existing / "old-marker.txt").exists()
    info = json.loads((existing / "repository_info.json").read_text())
    assert info["name"] == "myrepo"


def test_import_same_uuid_copy_creates_new_uuid(app_client):
    c, home, eval_dir = app_client
    project_uuid = str(uuid.uuid4())
    existing = eval_dir / project_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": project_uuid, "name": "original", "location": "local", "path": "/tmp/myrepo",
    }))
    data = _make_zip(project_uuid=project_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data, action="copy")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] != project_uuid
    assert body["sourceProjectId"] == project_uuid
    assert body["renamed"] is True
    # Existing project still there
    assert existing.exists()
    new_path = eval_dir / body["projectId"]
    assert new_path.exists()
    info = json.loads((new_path / "repository_info.json").read_text())
    assert info["uuid"] == body["projectId"]  # rewritten to new uuid


def test_import_same_identity_collision_returns_409(app_client):
    """Different UUID, same repo identity (name+path+scope) → 409 same_identity."""
    c, home, eval_dir = app_client
    existing_uuid = str(uuid.uuid4())
    incoming_uuid = str(uuid.uuid4())
    existing = eval_dir / existing_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": existing_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    data = _make_zip(project_uuid=incoming_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["kind"] == "same_identity"
    assert body["existingProjectId"] == existing_uuid


def test_import_same_identity_copy_creates_new_uuid(app_client):
    c, home, eval_dir = app_client
    existing_uuid = str(uuid.uuid4())
    incoming_uuid = str(uuid.uuid4())
    existing = eval_dir / existing_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": existing_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    data = _make_zip(project_uuid=incoming_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data, action="copy")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == incoming_uuid  # no UUID collision so we kept incoming uuid
    # both projects exist
    assert (eval_dir / existing_uuid).exists()
    assert (eval_dir / incoming_uuid).exists()


def test_import_same_identity_replace_is_refused(app_client):
    """'replace' on identity collision is ambiguous → must refuse, not pick a target."""
    c, home, eval_dir = app_client
    existing_uuid = str(uuid.uuid4())
    incoming_uuid = str(uuid.uuid4())
    existing = eval_dir / existing_uuid
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": existing_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    data = _make_zip(project_uuid=incoming_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data, action="replace")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "AMBIGUOUS_REPLACE"
