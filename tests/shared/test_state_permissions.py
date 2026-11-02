"""The state directory and its databases are owner-only after startup."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from quodeq.shared.state_permissions import secure_state_dir

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _env(root: Path) -> dict[str, str]:
    return {"QUODEQ_DIR": str(root), "QUODEQ_EVALUATIONS_DIR": str(root / "evaluations")}


def test_creates_a_missing_root_owner_only(tmp_path):
    root = tmp_path / "state"
    secure_state_dir(_env(root))
    assert _mode(root) == 0o700


def test_tightens_an_existing_root_and_every_database(tmp_path):
    root = tmp_path / "state"
    run = root / "evaluations" / "proj" / "run-1"
    run.mkdir(parents=True)
    root.chmod(0o755)
    dbs = [root / "index.db", root / "score_cache.db-wal", root / "assistant.db",
           root / "evaluations" / "proj" / "verifications.db", run / "evaluation.db", run / "evaluation.db-shm"]
    for db in dbs:
        db.write_text("x")
        db.chmod(0o644)
    (run / "events.jsonl").write_text("{}\n")
    (run / "events.jsonl").chmod(0o644)

    assert secure_state_dir(_env(root)) == len(dbs) + 1
    assert _mode(root) == 0o700
    assert {_mode(db) for db in dbs} == {0o600}
    assert _mode(run / "events.jsonl") == 0o644  # closed off by the root, left as it is
    assert secure_state_dir(_env(root)) == 0  # nothing left to change


def test_never_follows_a_symlinked_database(tmp_path):
    outside = tmp_path / "outside.db"
    outside.write_text("x")
    outside.chmod(0o644)
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    os.symlink(outside, root / "index.db")
    secure_state_dir(_env(root))
    assert _mode(outside) == 0o644
