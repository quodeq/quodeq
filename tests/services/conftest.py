import os
import stat
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore


def seed_security_findings(store: SQLiteStateStore, run_dir: Path) -> None:
    """Record 6 security violations and 8 compliance findings under practice p1,
    then bake default-params grades.

    Marks the (empty) events.jsonl as fully projected first so ensure_projected
    is a no-op and won't wipe the grades baked here.
    """
    for i in range(6):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", req=f"req{i}",
            verdict="violation", severity="major", file=f"f{i}.py", line=1,
            title=f"t{i}", reason=f"r{i}",
        ))
    for i in range(8):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", req=f"c{i}",
            verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
            title=f"ct{i}", reason=f"cr{i}",
        ))
    store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
    recompute_grades(run_dir, params=DEFAULT_PARAMS)


@pytest.fixture
def windows_unlink_semantics(monkeypatch):
    """Make os.unlink refuse read-only files, like Windows (WinError 5).

    POSIX deletion only checks the parent directory, so tests for git-tree
    cleanup (git marks object files read-only) pass trivially on macOS/Linux
    even when the code under test would fail on Windows. This fixture
    reproduces the Windows failure mode so those tests are meaningful on
    every platform. Deletion code must clear the read-only bit before
    retrying the unlink (see quodeq.data.fs.shared_repo.remove_clone_dir).
    """
    real_unlink = os.unlink

    def unlink(path, *args, dir_fd=None, **kwargs):
        mode = os.stat(path, dir_fd=dir_fd, follow_symlinks=False).st_mode
        if not mode & stat.S_IWRITE:
            raise PermissionError(5, "Access is denied", str(path))
        return real_unlink(path, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
