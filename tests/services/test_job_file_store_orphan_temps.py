"""FileJobStore removes old orphan ``*.tmp`` files on startup and keeps recent ones,
and a job file that cannot be unlinked does not fail ``delete``."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from quodeq.services.jobs import FileJobStore, Job

_ONE_DAY_S = timedelta(days=1).total_seconds()


def test_old_orphan_temp_is_removed_and_a_recent_one_kept(tmp_path: Path):
    old = tmp_path / "job-a.abc123.tmp"
    recent = tmp_path / "job-b.def456.tmp"
    old.write_text("{", encoding="utf-8")
    recent.write_text("{", encoding="utf-8")
    stale = time.time() - _ONE_DAY_S
    os.utime(old, (stale, stale))

    FileJobStore(persist_dir=tmp_path)

    assert not old.exists()
    assert recent.exists()


def test_delete_tolerates_unlink_failure(tmp_path: Path, monkeypatch, caplog):
    store = FileJobStore(persist_dir=tmp_path)
    store.put(Job("j1", "done", ["echo"], "now", "later", 0))
    monkeypatch.setattr(Path, "unlink", Mock(side_effect=PermissionError("busy")))
    store.delete("j1")  # must not raise
    assert store.get("j1") is None
    assert "job file" in caplog.text


def test_startup_tolerates_a_stale_job_file_that_cannot_be_removed(tmp_path: Path, monkeypatch, caplog):
    ended = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    FileJobStore(persist_dir=tmp_path).put(Job("old", "done", ["echo"], ended, ended, 0))
    monkeypatch.setattr(Path, "unlink", Mock(side_effect=PermissionError("busy")))
    store = FileJobStore(persist_dir=tmp_path)  # must not raise
    assert store.get("old") is None
    assert "stale job file" in caplog.text
