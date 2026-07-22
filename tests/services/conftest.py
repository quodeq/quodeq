import os
import stat

import pytest


@pytest.fixture
def windows_unlink_semantics(monkeypatch):
    """Make os.unlink refuse read-only files, like Windows (WinError 5).

    POSIX deletion only checks the parent directory, so tests for git-tree
    cleanup (git marks object files read-only) pass trivially on macOS/Linux
    even when the code under test would fail on Windows. This fixture
    reproduces the Windows failure mode so those tests are meaningful on
    every platform. Deletion code must clear the read-only bit before
    retrying the unlink (see quodeq.services.shared_repo.remove_clone_dir).
    """
    real_unlink = os.unlink

    def unlink(path, *args, dir_fd=None, **kwargs):
        mode = os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode
        if not mode & stat.S_IWRITE:
            raise PermissionError(5, "Access is denied", str(path))
        return real_unlink(path, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
