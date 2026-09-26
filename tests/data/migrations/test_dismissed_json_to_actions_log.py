from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import quodeq.data.actions_log as actions_log_mod
from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.data.actions_log import ActionLogWriter, read_action_events
from quodeq.data.migrations.dismissed_json_to_actions_log import (
    MIGRATION_MARKER,
    migrate_if_needed,
)

_LOGGER_NAME = "quodeq.data.migrations.dismissed_json_to_actions_log"


def _write_dismissed_json(project_dir: Path, entries: list[dict]) -> None:
    (project_dir / "dismissed.json").write_text(json.dumps(entries), encoding="utf-8")


def test_migration_creates_actions_log_from_dismissed_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [
        {"req": "R1", "file": "a.py", "line": 10, "dismissed_at": "2026-01-01T00:00:00Z"},
        {"req": "R2", "file": "b.py", "line": 20, "dismissed_at": "2026-01-02T00:00:00Z"},
    ])

    migrated = migrate_if_needed(project_dir)

    assert migrated == 2
    events = list(read_action_events(project_dir))
    assert len(events) == 2
    assert events[0].payload.req == "R1"
    assert events[1].payload.req == "R2"


def test_folds_legacy_even_when_actions_log_already_exists(tmp_path: Path) -> None:
    """A user who dismisses a finding before the migration ever runs creates
    actions.jsonl first. The legacy dismissed.json must STILL be folded in,
    not skipped, otherwise every pre-1.2.0 dismissal is silently orphaned."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [
        {"req": "R1", "file": "a.py", "line": 10},
        {"req": "R2", "file": "b.py", "line": 20},
    ])
    # Simulate the user dismissing a NEW finding first, which creates actions.jsonl.
    ActionLogWriter(project_dir).emit(FindingDismissedEvent(
        payload=FindingDismissed(req="R3", file="c.py", line=30, reason=None)
    ))

    migrated = migrate_if_needed(project_dir)

    assert migrated == 2
    reqs = {e.payload.req for e in read_action_events(project_dir)}
    assert reqs == {"R1", "R2", "R3"}


def test_idempotent_after_first_migration(tmp_path: Path) -> None:
    """Once folded, a second call is a no-op and does not duplicate events,
    even though dismissed.json is intentionally left on disk."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [{"req": "R1", "file": "a.py", "line": 10}])

    first = migrate_if_needed(project_dir)
    second = migrate_if_needed(project_dir)

    assert first == 1
    assert second == 0
    assert len(list(read_action_events(project_dir))) == 1


def test_migration_no_op_when_no_dismissed_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert migrate_if_needed(project_dir) == 0
    assert not (project_dir / "actions.jsonl").exists()


def test_migration_preserves_dismissed_json_as_fallback(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [{"req": "R1", "file": "a.py", "line": 10}])

    migrate_if_needed(project_dir)

    # JSON file is intentionally left in place for one release.
    assert (project_dir / "dismissed.json").exists()


def test_non_dict_entry_is_skipped_with_warning(tmp_path: Path, caplog) -> None:
    """A non-dict entry (a shape bug in the legacy file) must not crash the
    fold: it is logged and skipped, and the well-formed entries still land."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, ["not-a-dict", {"req": "R1", "file": "a.py", "line": 10}])

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        migrated = migrate_if_needed(project_dir)

    assert migrated == 1
    assert {e.payload.req for e in read_action_events(project_dir)} == {"R1"}
    assert any("non-dict" in r.message for r in caplog.records)


def test_entry_with_unconvertible_line_is_skipped_with_warning(tmp_path: Path, caplog) -> None:
    """A malformed value (line that doesn't convert to int) is a TypeError/
    ValueError from the conversion step, not a shape problem: logged and
    skipped like the non-dict case, the rest of the fold still runs."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [
        {"req": "R1", "file": "a.py", "line": "not-a-number"},
        {"req": "R2", "file": "b.py", "line": 20},
    ])

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        migrated = migrate_if_needed(project_dir)

    assert migrated == 1
    assert {e.payload.req for e in read_action_events(project_dir)} == {"R2"}
    assert any("Failed to migrate" in r.message for r in caplog.records)


def test_emit_failure_leaves_marker_absent_and_a_retry_migrates(
    tmp_path: Path, monkeypatch,
) -> None:
    """An OSError from writer.emit (a genuine write failure) is not caught
    by the per-entry conversion guard: it must propagate so the done marker
    is never written, and the next call retries the whole fold."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [{"req": "R1", "file": "a.py", "line": 10}])

    real_emit = actions_log_mod.ActionLogWriter.emit
    calls = {"n": 0}

    def flaky_emit(self, event):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        return real_emit(self, event)

    monkeypatch.setattr(actions_log_mod.ActionLogWriter, "emit", flaky_emit)

    with pytest.raises(OSError, match="disk full"):
        migrate_if_needed(project_dir)

    assert not (project_dir / MIGRATION_MARKER).exists()

    migrated = migrate_if_needed(project_dir)

    assert migrated == 1
    assert (project_dir / MIGRATION_MARKER).exists()
    assert {e.payload.req for e in read_action_events(project_dir)} == {"R1"}


def test_injected_locks_are_used_and_resettable(tmp_path: Path) -> None:
    from quodeq.data.migrations.dismissed_json_to_actions_log import (
        _DEFAULT_LOCKS, _MigrationLocks)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [{"req": "R1", "file": "a.py", "line": 10}])

    locks = _MigrationLocks()
    assert migrate_if_needed(project_dir, locks=locks) == 1

    # the injected table, not the process-wide one, took the lock
    assert locks.for_project(project_dir) is not _DEFAULT_LOCKS.for_project(project_dir)
    locks.reset()
    assert migrate_if_needed(project_dir, locks=locks) == 0
