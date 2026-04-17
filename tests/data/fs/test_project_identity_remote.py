"""Tests verifying that the same remote resolves to a single UUID across paths."""
from __future__ import annotations


def test_same_remote_different_paths_resolve_to_same_uuid(tmp_path):
    from quodeq.data.fs._models import ProjectIdentity
    from quodeq.data.fs.project_resolver import resolve_project_uuid

    reports = tmp_path / "evaluations"
    reports.mkdir()

    remote = "github.com/quodeq/quodeq"
    id_a = ProjectIdentity("quodeq", "/Users/alice/code/quodeq", location="local", remote_url=remote)
    id_b = ProjectIdentity("quodeq", "/Users/alice/ci/_work/quodeq/quodeq", location="local", remote_url=remote)

    uuid_a = resolve_project_uuid(reports, id_a)
    uuid_b = resolve_project_uuid(reports, id_b)
    assert uuid_a == uuid_b


def test_different_remotes_resolve_to_different_uuids(tmp_path):
    from quodeq.data.fs._models import ProjectIdentity
    from quodeq.data.fs.project_resolver import resolve_project_uuid

    reports = tmp_path / "evaluations"
    reports.mkdir()

    id_a = ProjectIdentity("foo", "/p1", location="local", remote_url="github.com/o/foo")
    id_b = ProjectIdentity("foo", "/p2", location="local", remote_url="github.com/o/bar")

    uuid_a = resolve_project_uuid(reports, id_a)
    uuid_b = resolve_project_uuid(reports, id_b)
    assert uuid_a != uuid_b


def test_legacy_path_based_entry_migrates_to_remote_key(tmp_path):
    """An existing project with only a path-based index key should be re-found
    when a new ProjectIdentity with a remote URL comes in, and the index should
    be updated to include the remote key."""
    from quodeq.data.fs._models import ProjectIdentity
    from quodeq.data.fs.project_resolver import resolve_project_uuid

    reports = tmp_path / "evaluations"
    reports.mkdir()

    # Simulate an old project resolved without remote_url.
    # Use tmp_path subdir so that Path.resolve() inside the resolver produces
    # a stable absolute path.
    legacy_path = tmp_path / "legacy" / "path"
    legacy_path.mkdir(parents=True)
    legacy_id = ProjectIdentity("quodeq", str(legacy_path), location="local")
    legacy_uuid = resolve_project_uuid(reports, legacy_id)

    # Now the same repo is accessed with a remote URL detected
    new_id = ProjectIdentity(
        "quodeq", str(legacy_path), location="local", remote_url="github.com/q/q"
    )
    new_uuid = resolve_project_uuid(reports, new_id)

    assert legacy_uuid == new_uuid


def test_no_remote_falls_back_to_path_identity(tmp_path):
    """Projects without a remote (e.g. local scratch dirs) still get path-based identity."""
    from quodeq.data.fs._models import ProjectIdentity
    from quodeq.data.fs.project_resolver import resolve_project_uuid

    reports = tmp_path / "evaluations"
    reports.mkdir()

    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    id_a = ProjectIdentity("scratch", str(dir_a), location="local")
    id_b = ProjectIdentity("scratch", str(dir_b), location="local")

    uuid_a = resolve_project_uuid(reports, id_a)
    uuid_b = resolve_project_uuid(reports, id_b)
    assert uuid_a != uuid_b
