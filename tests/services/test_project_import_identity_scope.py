"""find_identity_collision's directory walk compares scopePath too.

The project on disk has no index entry, so only the walk can find it.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.project_import_identity import find_identity_collision
from quodeq.services.project_index import ProjectIdentity, save_index


def _identity(scope_path: str | None) -> ProjectIdentity:
    return ProjectIdentity(
        project_name="demo", repo_path="/repo/demo", discipline=None,
        location="local", scope_path=scope_path, remote_url=None,
    )


def _project_on_disk(reports_root: Path, uuid: str, scope_path: str) -> None:
    project_dir = reports_root / uuid
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text(json.dumps({
        "uuid": uuid, "name": "demo", "path": "/repo/demo",
        "location": "local", "scopePath": scope_path,
    }))


def test_a_record_differing_only_in_scope_path_is_no_collision(tmp_path: Path):
    save_index(tmp_path, {})
    _project_on_disk(tmp_path, "other-uuid", scope_path="lib")

    result = find_identity_collision(tmp_path, _identity("pkg"), ignore_uuid="new-uuid")

    assert result is None


def test_an_empty_scope_path_matches_no_scope(tmp_path: Path):
    save_index(tmp_path, {})
    _project_on_disk(tmp_path, "other-uuid", scope_path="")

    result = find_identity_collision(tmp_path, _identity(None), ignore_uuid="new-uuid")

    assert result == "other-uuid"
