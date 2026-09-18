"""Tests for POST /api/projects/import: archive validation and layout checks."""
from __future__ import annotations

import io
import json
import uuid
import zipfile

import pytest

from quodeq.api.zip import _MANIFEST_FILENAME, _MANIFEST_KIND, _MANIFEST_SCHEMA
from tests.api._project_import_fixtures import (  # noqa: F401 -- app_client is a pytest fixture
    _ORIGIN,
    _make_zip,
    _patch_home,
    _post_zip,
    app_client,
)


def test_import_happy_path_creates_project_dir(app_client):
    c, home, eval_dir = app_client
    project_uuid = str(uuid.uuid4())
    data = _make_zip(project_uuid=project_uuid)
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == project_uuid
    assert body["sourceProjectId"] == project_uuid
    assert body["renamed"] is False
    assert (eval_dir / project_uuid / "repository_info.json").exists()


def test_import_missing_file_returns_400(app_client):
    c, home, _ = app_client
    with _patch_home(home):
        resp = c.post("/api/projects/import", data={}, content_type="multipart/form-data", headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_FILE"


def test_import_invalid_action_returns_400(app_client):
    c, home, _ = app_client
    data = _make_zip()
    with _patch_home(home):
        resp = _post_zip(c, data, action="nuke")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_ACTION"


def test_import_rejects_path_traversal(app_client):
    c, home, eval_dir = app_client
    # A second top-level entry trying to escape — the single-top-dir guard
    # should fire first, but either way the file must not appear outside the dir.
    project_uuid = str(uuid.uuid4())
    data = _make_zip(
        project_uuid=project_uuid,
        extra_member=("../escape.txt", b"pwned"),
    )
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] in {"INVALID_ARCHIVE", "BAD_LAYOUT"}
    # Nothing should have been written outside the reports dir.
    assert not (eval_dir.parent / "escape.txt").exists()


def test_import_rejects_absolute_member(app_client):
    c, home, _ = app_client
    project_uuid = str(uuid.uuid4())
    data = _make_zip(
        project_uuid=project_uuid,
        extra_member=("/etc/passwd", b"x"),
    )
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400


def test_import_rejects_symlink_entry(app_client):
    c, home, _ = app_client
    data = _make_zip(add_symlink_entry=True)
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    assert resp.get_json()["code"] in {"DISALLOWED_ENTRY", "INVALID_ARCHIVE"}


def test_import_rejects_backslashes_in_member_name():
    """The backslash check is defense-in-depth: stdlib zipfile normalises
    os.sep to "/" on Windows both when writing and when reading the central
    directory, so a HTTP-level test can't exercise this branch on Windows.
    Test the validator directly instead.
    """
    from quodeq.api.import_project import _ImportError, _validate_member_name
    with pytest.raises(_ImportError) as exc:
        _validate_member_name("uuid\\repository_info.json")
    assert "backslash" in str(exc.value).lower()


def test_import_rejects_multiple_top_dirs(app_client):
    c, home, _ = app_client
    project_uuid = str(uuid.uuid4())
    data = _make_zip(
        project_uuid=project_uuid,
        extra_member=("other-top/file.txt", b"x"),
    )
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_LAYOUT"


def test_import_rejects_non_uuid_top_dir(app_client):
    c, home, _ = app_client
    # build a zip with a top-dir that isn't a UUID by passing a non-UUID name
    data = _make_zip(project_uuid="not-a-uuid")
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_LAYOUT"


def test_import_rejects_non_zip(app_client):
    c, home, _ = app_client
    with _patch_home(home):
        resp = _post_zip(c, b"this is not a zip")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_ZIP"


def test_import_rejects_missing_repository_info(app_client):
    c, home, _ = app_client
    # Build a zip with only a manifest, no repository_info.json
    project_uuid = str(uuid.uuid4())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "schema": _MANIFEST_SCHEMA, "kind": _MANIFEST_KIND, "source_uuid": project_uuid,
        }
        zf.writestr(f"{project_uuid}/{_MANIFEST_FILENAME}", json.dumps(manifest))
    with _patch_home(home):
        resp = _post_zip(c, buf.getvalue())
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "MISSING_REPO_INFO"


def test_import_rejects_bad_manifest_schema(app_client):
    c, home, _ = app_client
    data = _make_zip(manifest_overrides={"schema": 99})
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_MANIFEST"


def test_import_rejects_bad_manifest_source_uuid(app_client):
    c, home, _ = app_client
    project_uuid = str(uuid.uuid4())
    data = _make_zip(
        project_uuid=project_uuid,
        manifest_overrides={"source_uuid": str(uuid.uuid4())},  # mismatches top dir
    )
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_MANIFEST"


def test_import_accepts_missing_manifest(app_client):
    """Older exports without manifest.json should still import."""
    c, home, eval_dir = app_client
    project_uuid = str(uuid.uuid4())
    data = _make_zip(project_uuid=project_uuid, include_manifest=False)
    with _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 200, resp.get_json()
    assert (eval_dir / project_uuid / "repository_info.json").exists()
