"""update_actions tolerates bad log content and surfaces store failures.

The actions log is folded into one net state: a malformed line is skipped by
the reader, an event of an unrelated type is ignored by the fold, and a
store failure while applying the state propagates without the projected
size being saved (so the next call retries instead of marking the unwritable
state as done).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _line(event_type: str, payload: dict) -> str:
    return json.dumps({
        "event_id": str(uuid.uuid4()),
        "timestamp": "2026-07-24T10:00:00Z",
        "event_type": event_type,
        "payload": payload,
    })


def _seed_finding(run_dir: Path) -> None:
    from quodeq.data.sqlite.connection import open_evaluation_db
    with open_evaluation_db(run_dir) as conn:
        conn.execute(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict,"
            " severity, file, line, dedup_key)"
            " VALUES ('P', 'maintainability', 'R-1', 'violation', 'major', 'a.kt', 1, 'k')",
        )
        conn.commit()


def _verdict(run_dir: Path) -> str:
    from quodeq.data.sqlite.connection import open_evaluation_db
    with open_evaluation_db(run_dir) as conn:
        return conn.execute("SELECT verdict FROM findings").fetchone()[0]


def test_update_actions_skips_malformed_and_unrelated_lines(tmp_path: Path) -> None:
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    _seed_finding(run_dir)
    log = tmp_path / "actions.jsonl"
    log.write_text("\n".join([
        "{not json",
        _line("FINDING_VERIFIED", {"req": "R-1", "file": "a.kt", "line": 1, "note": "n"}),
        _line("FINDING_DISMISSED", {"req": "R-1", "file": "a.kt", "line": 1, "reason": None}),
    ]) + "\n", encoding="utf-8")

    changed = ProjectionEngine().update_actions(log, run_dir)

    assert changed == 1
    assert _verdict(run_dir) == "dismissed"


def test_store_failure_propagates_and_leaves_size_unsaved(tmp_path: Path) -> None:
    """A DB failure is not "one bad event": it must surface, and the projected
    size must not be saved, so the next call applies the state again."""
    log = tmp_path / "actions.jsonl"
    log.write_text(
        _line("FINDING_DISMISSED", {"req": "R-1", "file": "a.kt", "line": 1, "reason": None}) + "\n",
        encoding="utf-8",
    )
    store = MagicMock(spec=SQLiteStateStore)
    store.get_actions_projected_size.return_value = None
    store.connection.return_value.__enter__ = lambda *a: None
    store.connection.return_value.__exit__ = lambda *a: False
    store.apply_dismissed_state.side_effect = RuntimeError("disk I/O error")

    with patch("quodeq.data.projection.engine.SQLiteStateStore", return_value=store):
        with pytest.raises(RuntimeError, match="disk I/O error"):
            ProjectionEngine().update_actions(log, tmp_path, force=True)

    store.save_actions_projected_size.assert_not_called()
