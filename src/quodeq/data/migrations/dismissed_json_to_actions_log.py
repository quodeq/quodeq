"""One-shot migration: fold project_dir/dismissed.json into actions.jsonl.

Runs lazily on first projection of a project. Idempotent -- skips when
actions.jsonl already exists. Leaves dismissed.json in place as a read-only
fallback for one release.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.data.actions_log import ACTIONS_LOG_FILENAME, ActionLogWriter

_logger = logging.getLogger(__name__)


def migrate_if_needed(project_dir: Path) -> int:
    """Fold dismissed.json into actions.jsonl. Returns count of entries migrated."""
    actions_log = project_dir / ACTIONS_LOG_FILENAME
    if actions_log.exists():
        return 0

    dismissed_json = project_dir / "dismissed.json"
    if not dismissed_json.is_file():
        return 0

    try:
        entries = json.loads(dismissed_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _logger.warning("Could not read %s during migration; skipping", dismissed_json)
        return 0
    if not isinstance(entries, list):
        return 0

    writer = ActionLogWriter(project_dir)
    count = 0
    for entry in entries:
        try:
            payload = FindingDismissed(
                req=str(entry.get("req", "")),
                file=str(entry.get("file", "")),
                line=int(entry.get("line", 0)),
                reason=None,
            )
            writer.emit(FindingDismissedEvent(payload=payload))
            count += 1
        except Exception:
            _logger.exception("Failed to migrate dismissed entry: %s", entry)
            continue
    _logger.info(
        "Migrated %d entries from dismissed.json to actions.jsonl in %s",
        count,
        project_dir,
    )
    return count
