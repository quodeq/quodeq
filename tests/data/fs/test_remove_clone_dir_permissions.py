"""A clone directory that cannot be fully removed stays readable.

Regression context: the rmtree retry handler cleared the read-only bit with
``chmod(S_IWRITE)``, which on a DIRECTORY strips read and search as well.
When a removal hit a directory that was still being written to (the shared
warm-up worker scoring a run while a disconnect deleted the clone), the
handler left that directory write-only, and the next connect could not
clone into it: "Couldn't clone the shared repository".
"""
from __future__ import annotations

import os
import stat
import sys

import pytest

from quodeq.data.fs.shared_repo import remove_clone_dir


def _readable(path) -> bool:
    mode = os.stat(path).st_mode
    return bool(mode & stat.S_IRUSR) and bool(mode & stat.S_IXUSR)


def test_a_read_only_file_is_still_removed(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    victim = root / "object"
    victim.write_text("x", encoding="utf-8")
    victim.chmod(stat.S_IREAD)

    remove_clone_dir(root)

    assert not root.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory modes")
def test_a_stuck_tree_is_left_readable(tmp_path):
    """A subtree whose parent forbids deletion cannot be removed; what stays must stay readable."""
    root = tmp_path / "clone"
    locked = root / "locked"
    locked.mkdir(parents=True)
    (locked / "child").write_text("x", encoding="utf-8")
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # no write: its child cannot be unlinked
    try:
        remove_clone_dir(root)
        assert root.exists()  # the stuck subtree keeps it alive
        for path in (root, locked):
            assert _readable(path), f"{path} was left unreadable"
    finally:
        for path in (locked, root):
            if path.exists():
                path.chmod(stat.S_IRWXU)
