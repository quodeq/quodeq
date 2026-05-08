"""Tests for POST /api/projects/import — project zip ingestion + collision resolution."""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.api.zip import _MANIFEST_FILENAME, _MANIFEST_KIND, _MANIFEST_SCHEMA

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evaluations_dir))
    app = create_app(test_config={"TESTING": True})
    home = tmp_path.resolve()
    with app.test_client() as c:
        yield c, home, evaluations_dir


def _patch_home(home: Path):
    return patch("pathlib.Path.home", new=classmethod(lambda cls: home))


def _make_zip(
    *,
    project_uuid: str | None = None,
    repo_info: dict | None = None,
    extra_files: dict[str, bytes] | None = None,
    include_manifest: bool = True,
    manifest_overrides: dict | None = None,
    extra_member: tuple[str, bytes] | None = None,
    add_symlink_entry: bool = False,
    raw_bytes: bytes | None = None,
) -> bytes:
    """Build an in-memory project zip. Returns the raw bytes."""
    if raw_bytes is not None:
        return raw_bytes
    project_uuid = project_uuid or str(uuid.uuid4())
    repo_info = repo_info or {
        "uuid": project_uuid,
        "name": "myrepo",
        "discipline": None,
        "location": "local",
        "path": "/tmp/myrepo",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{project_uuid}/repository_info.json", json.dumps(repo_info))
        if include_manifest:
            manifest = {
                "schema": _MANIFEST_SCHEMA,
                "kind": _MANIFEST_KIND,
                "source_uuid": project_uuid,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            if manifest_overrides:
                manifest.update(manifest_overrides)
            zf.writestr(f"{project_uuid}/{_MANIFEST_FILENAME}", json.dumps(manifest))
        for name, data in (extra_files or {}).items():
            zf.writestr(f"{project_uuid}/{name}", data)
        if extra_member is not None:
            arc, data = extra_member
            zf.writestr(arc, data)
        if add_symlink_entry:
            info = zipfile.ZipInfo(f"{project_uuid}/evil-link")
            info.create_system = 3  # Unix
            info.external_attr = (0xA1FF) << 16  # symlink mode bits in upper half
            zf.writestr(info, "../../etc/passwd")
    return buf.getvalue()


def _post_zip(client, data: bytes, *, action: str | None = None, filename: str = "project.zip"):
    payload = {"file": (io.BytesIO(data), filename)}
    if action is not None:
        payload["action"] = action
    return client.post(
        "/api/projects/import",
        data=payload,
        content_type="multipart/form-data",
        headers=_ORIGIN,
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


def test_import_oversize_returns_413(app_client, monkeypatch):
    c, home, _ = app_client
    # Force a tiny size limit so any well-formed zip trips it.
    monkeypatch.setenv("QUODEQ_MAX_ZIP_SIZE_MB", "0")
    # Build a fresh app with the small limit so MAX_CONTENT_LENGTH picks it up.
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as small_c, _patch_home(home):
        data = _make_zip(extra_files={"big.txt": b"x" * 10_000})
        resp = small_c.post(
            "/api/projects/import",
            data={"file": (io.BytesIO(data), "p.zip")},
            content_type="multipart/form-data",
            headers=_ORIGIN,
        )
    assert resp.status_code in (413,)


def test_import_zip_bomb_ratio_rejected(app_client):
    """A small compressed entry that decompresses to >> 200x triggers the ratio guard."""
    c, home, _ = app_client
    project_uuid = str(uuid.uuid4())
    # Build a zip with a single highly-compressible 5MB entry
    repo_info = {"uuid": project_uuid, "name": "myrepo", "location": "local", "path": "/tmp/r"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{project_uuid}/repository_info.json", json.dumps(repo_info))
        # 5 MB of zeros — compresses to a few KB → ratio >> 200
        zf.writestr(f"{project_uuid}/bomb.bin", b"\x00" * (5 * 1024 * 1024))
    with _patch_home(home):
        resp = _post_zip(c, buf.getvalue())
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "BAD_RATIO"


def test_import_export_roundtrip(app_client):
    """Export a project, then import the resulting zip — should land identically."""
    from quodeq.api.zip import _build_project_zip
    c, home, eval_dir = app_client
    src_uuid = str(uuid.uuid4())
    src = eval_dir / src_uuid
    src.mkdir()
    (src / "repository_info.json").write_text(json.dumps({
        "uuid": src_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    (src / "scan.json").write_text(json.dumps({"total_files": 7}))
    zip_path = _build_project_zip(src)
    try:
        zip_bytes = zip_path.read_bytes()
    finally:
        zip_path.unlink()
    # Delete original so import doesn't hit a collision
    import shutil
    shutil.rmtree(src)
    with _patch_home(home):
        resp = _post_zip(c, zip_bytes)
    assert resp.status_code == 200, resp.get_json()
    assert (eval_dir / src_uuid / "scan.json").exists()
