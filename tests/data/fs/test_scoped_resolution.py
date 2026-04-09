"""Tests for scope-aware project resolution with parent/child creation."""
import json
from pathlib import Path

from quodeq.data.fs.project_resolver import (
    ProjectIdentity,
    clear_index_cache,
    resolve_project_uuid,
)


def _read_info(reports_dir: Path, uuid: str) -> dict:
    return json.loads((reports_dir / uuid / "repository_info.json").read_text())


def test_scoped_creates_parent_and_child(tmp_path: Path) -> None:
    """A scoped identity creates both a parent (full repo) and a child (scoped) directory."""
    clear_index_cache()
    identity = ProjectIdentity(
        project_name="myrepo",
        repo_path=str(tmp_path / "repo"),
        discipline="python",
        scope_path="src/api",
    )
    child_uuid = resolve_project_uuid(tmp_path / "reports", identity)

    # Child dir must exist with scopePath and parent
    child_info = _read_info(tmp_path / "reports", child_uuid)
    assert child_info["scopePath"] == "src/api"
    assert "parent" in child_info
    parent_uuid = child_info["parent"]

    # Parent dir must exist without scopePath or parent
    parent_info = _read_info(tmp_path / "reports", parent_uuid)
    assert "scopePath" not in parent_info
    assert "parent" not in parent_info
    assert parent_info["name"] == "myrepo"

    # Child name is parent_name/scope_path
    assert child_info["name"] == "myrepo/src/api"


def test_scoped_reuses_existing_parent(tmp_path: Path) -> None:
    """If the parent project already exists, the scoped resolution reuses it."""
    clear_index_cache()
    reports = tmp_path / "reports"
    repo_path = str(tmp_path / "repo")

    # Create parent first (unscoped)
    parent_identity = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        discipline="python",
    )
    parent_uuid = resolve_project_uuid(reports, parent_identity)

    # Now create scoped child
    child_identity = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        discipline="python",
        scope_path="src/api",
    )
    child_uuid = resolve_project_uuid(reports, child_identity)

    child_info = _read_info(reports, child_uuid)
    assert child_info["parent"] == parent_uuid
    assert child_uuid != parent_uuid

    # Only 2 project directories should exist (parent + child)
    project_dirs = [d for d in reports.iterdir() if d.is_dir() and not d.name.startswith(".")]
    assert len(project_dirs) == 2


def test_same_scope_reuses_child(tmp_path: Path) -> None:
    """Resolving the same scope_path twice returns the same child UUID."""
    clear_index_cache()
    reports = tmp_path / "reports"
    repo_path = str(tmp_path / "repo")

    identity = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        scope_path="src/api",
    )
    uuid1 = resolve_project_uuid(reports, identity)
    uuid2 = resolve_project_uuid(reports, identity)
    assert uuid1 == uuid2


def test_different_scopes_create_different_children(tmp_path: Path) -> None:
    """Different scope_paths produce different child UUIDs."""
    clear_index_cache()
    reports = tmp_path / "reports"
    repo_path = str(tmp_path / "repo")

    id_api = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        scope_path="src/api",
    )
    id_web = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        scope_path="src/web",
    )
    uuid_api = resolve_project_uuid(reports, id_api)
    uuid_web = resolve_project_uuid(reports, id_web)
    assert uuid_api != uuid_web

    # Both share the same parent
    info_api = _read_info(reports, uuid_api)
    info_web = _read_info(reports, uuid_web)
    assert info_api["parent"] == info_web["parent"]


def test_unscoped_resolution_unchanged(tmp_path: Path) -> None:
    """Without scope_path, resolution behaves exactly as before."""
    clear_index_cache()
    reports = tmp_path / "reports"
    repo_path = str(tmp_path / "repo")

    identity = ProjectIdentity(
        project_name="myrepo",
        repo_path=repo_path,
        discipline="python",
    )
    uuid1 = resolve_project_uuid(reports, identity)
    uuid2 = resolve_project_uuid(reports, identity)
    assert uuid1 == uuid2

    info = _read_info(reports, uuid1)
    assert "scopePath" not in info
    assert "parent" not in info
    assert info["name"] == "myrepo"
