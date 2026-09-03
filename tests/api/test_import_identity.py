from __future__ import annotations

import json
from pathlib import Path

from quodeq.api._import_identity import _find_identity_collision
from quodeq.services.project_index import ProjectIdentity, index_key, load_index, save_index


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


def test_self_match_in_index_still_falls_through_to_directory_walk(tmp_path: Path):
    """A self-match index entry (identity -> ignore_uuid) must not short-circuit
    the fallback walk: a different, non-indexed legacy project on disk can
    still collide with this identity, and the walk is the only thing that
    would find it.
    """
    identity = _identity()
    save_index(tmp_path, {index_key(identity): "new-uuid"})

    legacy = tmp_path / "legacy-uuid"
    legacy.mkdir()
    (legacy / "repository_info.json").write_text(json.dumps({
        "uuid": "legacy-uuid",
        "name": identity.project_name,
        "path": identity.repo_path,
        "location": identity.location,
    }))

    result = _find_identity_collision(tmp_path, identity, ignore_uuid="new-uuid")
    assert result == "legacy-uuid"


def test_falls_back_to_directory_walk_when_index_misses_and_self_heals(tmp_path: Path):
    """A project whose repository_info.json predates the index (or whose index
    write silently failed) has no index entry. The index-only fast path would
    silently miss the collision; the directory-walk fallback must still find
    it, and it must repair the index so the next lookup takes the fast path.
    """
    identity = _identity()
    existing = tmp_path / "existing-uuid"
    existing.mkdir()
    (existing / "repository_info.json").write_text(json.dumps({
        "uuid": "existing-uuid",
        "name": identity.project_name,
        "path": identity.repo_path,
        "location": identity.location,
    }))
    # No index at all — simulates a legacy project or a best-effort index
    # write that never happened.
    assert load_index(tmp_path) == {}

    result = _find_identity_collision(tmp_path, identity, ignore_uuid="new-uuid")
    assert result == "existing-uuid"

    # Self-heal: the fallback hit must have been written back into the index.
    index = load_index(tmp_path)
    assert index[index_key(identity)] == "existing-uuid"

    # A second lookup now hits the fast path even if repository_info.json
    # disappears (proving it no longer needs the directory walk).
    (existing / "repository_info.json").unlink()
    result_again = _find_identity_collision(tmp_path, identity, ignore_uuid="new-uuid")
    assert result_again == "existing-uuid"
