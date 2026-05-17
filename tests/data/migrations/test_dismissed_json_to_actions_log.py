from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.actions_log import ActionLogWriter, read_action_events
from quodeq.data.migrations.dismissed_json_to_actions_log import migrate_if_needed


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


def test_migration_idempotent_when_actions_log_exists(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_dismissed_json(project_dir, [{"req": "R1", "file": "a.py", "line": 10}])
    (project_dir / "actions.jsonl").write_text("")  # exists, even if empty

    migrated = migrate_if_needed(project_dir)

    assert migrated == 0


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
