from __future__ import annotations

import json
from pathlib import Path

from quodeq.api._import_identity import _find_identity_collision
from quodeq.services.project_index import ProjectIdentity, index_key, save_index


def _identity(**kw) -> ProjectIdentity:
    defaults = dict(
        project_name="demo", repo_path="/repo/demo", discipline=None,
        location="local", scope_path=None, remote_url=None,
    )
    defaults.update(kw)
    return ProjectIdentity(**defaults)


def test_finds_collision_via_index_without_reading_repository_info(tmp_path: Path):
    identity = _identity()
    save_index(tmp_path, {index_key(identity): "existing-uuid"})
    # No repository_info.json anywhere on disk — a directory-walk fallback
    # would find nothing; the index lookup must still find the collision.
    (tmp_path / "existing-uuid").mkdir()

    result = _find_identity_collision(tmp_path, identity, ignore_uuid="new-uuid")
    assert result == "existing-uuid"


def test_no_collision_when_index_has_no_matching_key(tmp_path: Path):
    save_index(tmp_path, {})
    result = _find_identity_collision(tmp_path, _identity(), ignore_uuid="new-uuid")
    assert result is None


def test_ignores_the_candidate_uuid_itself(tmp_path: Path):
    identity = _identity()
    save_index(tmp_path, {index_key(identity): "self-uuid"})
    result = _find_identity_collision(tmp_path, identity, ignore_uuid="self-uuid")
    assert result is None
