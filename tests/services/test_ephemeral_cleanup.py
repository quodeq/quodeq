from pathlib import Path
import pytest
from quodeq.services._ephemeral_cleanup import delete_ephemeral_clone, sweep_orphaned_clones


def test_delete_ephemeral_clone_removes_directory(tmp_path):
    clones_root = tmp_path / "clones"
    project_uuid = "abc-123"
    clone_dir = clones_root / project_uuid
    clone_dir.mkdir(parents=True)
    (clone_dir / "file.txt").write_text("hello")

    delete_ephemeral_clone(clones_root, project_uuid)

    assert not clone_dir.exists()
    assert clones_root.exists()  # parent untouched


def test_delete_ephemeral_clone_missing_dir_is_noop(tmp_path):
    clones_root = tmp_path / "clones"
    clones_root.mkdir()
    delete_ephemeral_clone(clones_root, "does-not-exist")  # must not raise


def test_delete_ephemeral_clone_rejects_path_traversal(tmp_path):
    clones_root = tmp_path / "clones"
    clones_root.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "important.txt").write_text("keep me")

    delete_ephemeral_clone(clones_root, "../sibling")

    assert sibling.exists()
    assert (sibling / "important.txt").exists()


def test_sweep_removes_orphans_keeps_registered(tmp_path):
    clones_root = tmp_path / "clones"
    reports_root = tmp_path / "reports"
    clones_root.mkdir()
    reports_root.mkdir()

    # Registered project
    (reports_root / "kept-uuid").mkdir()
    (clones_root / "kept-uuid").mkdir()
    # Orphan
    (clones_root / "orphan-uuid").mkdir()

    sweep_orphaned_clones(clones_root, reports_root)

    assert (clones_root / "kept-uuid").exists()
    assert not (clones_root / "orphan-uuid").exists()


def test_sweep_handles_missing_clones_root(tmp_path):
    sweep_orphaned_clones(tmp_path / "no-such-dir", tmp_path)  # must not raise


# --- Windows-safe deletion of git trees ----------------------------------
# Git marks object files read-only and Windows refuses to unlink those, so
# rmtree with a log-only onexc handler left ephemeral clones behind. Both
# entry points must clear the read-only bit and retry (via
# shared_repo.remove_clone_dir). The windows_unlink_semantics fixture makes
# the failure reproducible on POSIX.


def _make_readonly_git_object(clone_dir: Path) -> Path:
    objects = clone_dir / ".git" / "objects" / "09"
    objects.mkdir(parents=True)
    blob = objects / "deadbeef"
    blob.write_bytes(b"x")
    blob.chmod(0o444)
    return blob


def test_delete_ephemeral_clone_clears_readonly_git_objects(
    tmp_path, windows_unlink_semantics
):
    clones_root = tmp_path / "clones"
    project_uuid = "abc-123"
    _make_readonly_git_object(clones_root / project_uuid)

    delete_ephemeral_clone(clones_root, project_uuid)

    assert not (clones_root / project_uuid).exists()


def test_sweep_clears_readonly_git_objects_in_orphans(
    tmp_path, windows_unlink_semantics
):
    clones_root = tmp_path / "clones"
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    _make_readonly_git_object(clones_root / "orphan-uuid")

    sweep_orphaned_clones(clones_root, reports_root)

    assert not (clones_root / "orphan-uuid").exists()
