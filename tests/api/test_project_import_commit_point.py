"""POST /api/projects/import: the rename of the staged project is the commit point.

A copy import gets a fresh UUID. That UUID is written into the staged
repository_info.json before the rename, so a failure before the rename
leaves no project directory and no staging tree, and a failure after it
leaves a complete project.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from tests.api._project_import_fixtures import (  # noqa: F401 -- app_client is a pytest fixture
    _make_zip,
    _patch_home,
    _post_zip,
    app_client,
)

_REPO_INFO = "repository_info.json"


def _existing_project(eval_dir: Path) -> str:
    project_uuid = str(uuid.uuid4())
    existing = eval_dir / project_uuid
    existing.mkdir()
    (existing / _REPO_INFO).write_text(json.dumps({
        "uuid": project_uuid, "name": "original", "location": "local", "path": "/tmp/myrepo",
    }))
    return project_uuid


def _copy_import(client, home: Path, project_uuid: str):
    with _patch_home(home):
        return _post_zip(client, _make_zip(project_uuid=project_uuid), action="copy")


def test_the_staged_tree_carries_the_new_uuid_when_it_is_renamed(app_client, monkeypatch):
    c, home, eval_dir = app_client
    project_uuid = _existing_project(eval_dir)
    real_rename = Path.rename
    seen: list[str] = []

    def _spy_rename(self, target):
        if self.name == project_uuid and self.parent.name.startswith("quodeq_import_"):
            seen.append(json.loads((self / _REPO_INFO).read_text())["uuid"])
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", _spy_rename)
    resp = _copy_import(c, home, project_uuid)
    assert resp.status_code == 200, resp.get_json()
    assert seen == [resp.get_json()["projectId"]]


def test_a_failed_uuid_write_before_the_rename_leaves_no_project(app_client, monkeypatch):
    c, home, eval_dir = app_client
    project_uuid = _existing_project(eval_dir)
    monkeypatch.setattr(
        "quodeq.services.project_import_identity.write_repository_info", lambda *_a, **_k: False,
    )
    resp = _copy_import(c, home, project_uuid)
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "IO_ERROR"
    assert sorted(p.name for p in eval_dir.iterdir()) == [project_uuid]


def test_a_failed_rename_leaves_no_project_and_no_staging(app_client, monkeypatch):
    c, home, eval_dir = app_client
    project_uuid = _existing_project(eval_dir)
    real_rename = Path.rename

    def _failing_rename(self, target):
        if self.name == project_uuid and self.parent.name.startswith("quodeq_import_"):
            raise OSError("rename failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", _failing_rename)
    resp = _copy_import(c, home, project_uuid)
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "IO_ERROR"
    assert sorted(p.name for p in eval_dir.iterdir()) == [project_uuid]


def test_a_failed_index_update_after_the_rename_leaves_a_complete_project(app_client, monkeypatch):
    c, home, eval_dir = app_client
    project_uuid = _existing_project(eval_dir)

    def _failing_save(*_args, **_kwargs):
        raise OSError("index write failed")

    monkeypatch.setattr("quodeq.services.project_import_identity.save_index", _failing_save)
    resp = _copy_import(c, home, project_uuid)
    assert resp.status_code == 200, resp.get_json()
    new_uuid = resp.get_json()["projectId"]
    info = json.loads((eval_dir / new_uuid / _REPO_INFO).read_text())
    assert info["uuid"] == new_uuid
    assert info["name"] == "myrepo"
    assert not list(eval_dir.glob("quodeq_import_*"))
