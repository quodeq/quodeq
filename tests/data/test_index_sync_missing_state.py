"""Regression: stale promotion must survive a status.json missing "state".

Split from test_index_sync.py (already at the 300-line file cap) rather than
grown in place.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from quodeq.data.fs.run_status_store import read_status
from quodeq.data.sqlite._index_sync import _check_stale_and_promote
from quodeq.data.sqlite.run_index import open_index


def _make_run_dir(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d


def test_stale_promotion_survives_status_json_missing_state(tmp_path: Path) -> None:
    """A status.json without a "state" key (hand-edited, or a partial write
    that never got that far) must still be promotable to cancelled.

    Regression for a refactor gap: RunStatus.from_status_dict indexes
    d["state"] directly, unlike the pre-refactor code, which only ever read
    "state" via status.get("state") and never dereferenced it again once
    past the terminal-state check -- every other field had its own .get()
    default. A missing key must not turn into a KeyError here.
    """
    db = open_index(tmp_path / "idx.db")
    try:
        run = _make_run_dir(tmp_path, "p", "r-no-state")
        (run / "status.json").write_text(json.dumps({
            "schema_version": 2,
            "job_id": "ext-r-no-state",
            "started_at": "2026-04-20T00:00:00+00:00",
            "dimensions": [],
            "pid": 999999999,
        }))
        heartbeat = run / ".heartbeat"
        heartbeat.touch()
        old = time.time() - 60
        os.utime(heartbeat, (old, old))

        promoted = _check_stale_and_promote(
            db, run, project_uuid="p", run_id="r-no-state", stale_seconds=30,
        )
        assert promoted is True

        disk = read_status(run)
        assert disk is not None
        assert disk["state"] == "cancelled"
        assert disk["exit_reason"] == "stale_detected"
    finally:
        db.close()
