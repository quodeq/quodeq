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
