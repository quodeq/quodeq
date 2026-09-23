"""Tests for POST /api/projects/import: size limits, export round-trip and index injection."""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from quodeq.api.app import create_app
from tests.api._project_import_fixtures import (  # noqa: F401 -- app_client is a pytest fixture
    _ORIGIN,
    _make_zip,
    _patch_home,
    _post_zip,
    app_client,
)


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


def test_import_uncompressed_over_limit_but_compressed_under_is_accepted(app_client):
    """The MB cap applies to the zip bytes; extraction gets bounded headroom
    so text that legitimately compresses well (evaluation data deflates ~5x)
    can round-trip through export and import."""
    c, home, _ = app_client
    # ~3 MiB uncompressed at a ~4x compression ratio -> well under a 1 MiB zip.
    payload = b"".join(os.urandom(64) + b"x" * 192 for _ in range(12288))
    data = _make_zip(extra_files={"evidence.jsonl": payload})
    assert len(data) < 1024 * 1024
    with patch("quodeq.api.import_project.max_zip_size_bytes", return_value=1024 * 1024), _patch_home(home):
        resp = _post_zip(c, data)
    assert resp.status_code == 200, resp.get_json()


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
    from quodeq.api.zip import build_project_zip
    c, home, eval_dir = app_client
    src_uuid = str(uuid.uuid4())
    src = eval_dir / src_uuid
    src.mkdir()
    (src / "repository_info.json").write_text(json.dumps({
        "uuid": src_uuid, "name": "myrepo", "location": "local", "path": "/tmp/myrepo",
    }))
    (src / "scan.json").write_text(json.dumps({"total_files": 7}))
    zip_path = build_project_zip(src)
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


# ---------------------------------------------------------------------------
# #2494 — update_index must use an injected repository when provided
# ---------------------------------------------------------------------------

class TestUpdateIndexDI:
    """update_index must delegate to the injected ProjectRepository when given."""

    def test_injected_repository_is_used_not_filesystem(self, tmp_path):
        """When a repository is injected, load_index/save_index on it are called
        instead of the default _load_index/_save_index filesystem helpers."""
        from quodeq.api.import_project import update_index
        from quodeq.data.fs._models import ProjectIdentity
        from quodeq.data.fs._resolution import _index_key

        captured_loads: list = []
        captured_saves: list = []

        class SpyRepository:
            def load_index(self, reports_dir: Path) -> dict[str, str]:
                captured_loads.append(reports_dir)
                return {}

            def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
                captured_saves.append((reports_dir, dict(index)))

        identity = ProjectIdentity(project_name="myrepo", repo_path="/tmp/myrepo")
        project_uuid = "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb"
        spy = SpyRepository()

        update_index(tmp_path, identity, project_uuid, repository=spy)

        assert len(captured_loads) == 1
        assert captured_loads[0] == tmp_path
        assert len(captured_saves) == 1
        saved_dir, saved_index = captured_saves[0]
        assert saved_dir == tmp_path
        assert saved_index[_index_key(identity)] == project_uuid

    def test_no_repository_uses_filesystem(self, tmp_path):
        """Without a repository, update_index writes to project_index.json on disk."""
        import json
        from quodeq.api.import_project import update_index
        from quodeq.data.fs._models import ProjectIdentity
        from quodeq.data.fs._resolution import _index_key

        identity = ProjectIdentity(project_name="testrepo", repo_path="/tmp/testrepo")
        project_uuid = "11112222-3333-4444-5555-666677778888"

        update_index(tmp_path, identity, project_uuid)

        index_file = tmp_path / "project_index.json"
        assert index_file.exists()
        data = json.loads(index_file.read_text())
        assert data[_index_key(identity)] == project_uuid
