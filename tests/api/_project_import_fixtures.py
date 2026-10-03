"""Shared fixtures and zip builders for tests/api/test_project_import*.py siblings."""
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
from quodeq.api.zip import MANIFEST_FILENAME, MANIFEST_KIND, MANIFEST_SCHEMA


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
                "schema": MANIFEST_SCHEMA,
                "kind": MANIFEST_KIND,
                "source_uuid": project_uuid,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            if manifest_overrides:
                manifest.update(manifest_overrides)
            zf.writestr(f"{project_uuid}/{MANIFEST_FILENAME}", json.dumps(manifest))
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
