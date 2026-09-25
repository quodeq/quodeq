"""One-shot migration: fold project_dir/dismissed.json into actions.jsonl.

Runs lazily the first time a project's dismissed state is read or written
(see quodeq.services.dismissed) and on first projection. Idempotency is keyed
off a sentinel marker file, NOT off actions.jsonl: a user can dismiss a
finding (creating actions.jsonl) before this migration ever runs, and the
legacy dismissed.json must STILL be folded in. Appending the legacy
FindingDismissed events is safe even when actions.jsonl already has entries --
the dismissed set is computed by replaying the log, so a key dismissed twice
is still just dismissed. dismissed.json is left in place as a read-only
fallback for one release.
"""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from pathlib import Path

from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.data.actions_log import ActionLogWriter

_logger = logging.getLogger(__name__)

#: Sentinel written next to dismissed.json once the fold has run. Its presence
#: (not actions.jsonl's) is what makes the migration idempotent.
MIGRATION_MARKER = ".dismissed_migrated"


class _MigrationLocks:
    """One lock per project so a concurrent first read + first write can't double-fold."""

    def __init__(self) -> None:
        self._locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)

    def for_project(self, project_dir: Path) -> threading.Lock:
        return self._locks[project_dir]

    def reset(self) -> None:
        self._locks.clear()


#: Process-wide default; pass ``locks=`` to migrate_if_needed to isolate a test.
_DEFAULT_LOCKS = _MigrationLocks()


def _fold_legacy_entries(writer: ActionLogWriter, entries: list) -> int:
    """Emit a FindingDismissed event for each legacy dismissed.json entry.

    Tolerant per-entry for shape and value problems: a non-dict entry, or one
    whose fields don't convert, is logged and skipped rather than aborting
    the whole fold. An ``OSError`` from ``writer.emit`` (a genuine write
    failure) is NOT caught here: it propagates out of ``migrate_if_needed``
    so the done marker is never written and the next call retries the fold.
    """
    count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            _logger.warning("Skipping non-dict dismissed entry: %r", entry)
            continue
        try:
            payload = FindingDismissed(
                req=str(entry.get("req", "")),
                file=str(entry.get("file", "")),
                line=int(entry.get("line", 0)),
                reason=None,
            )
        except (TypeError, ValueError):
            _logger.warning("Failed to migrate dismissed entry: %s", entry)
            continue
        writer.emit(FindingDismissedEvent(payload=payload))
        count += 1
    return count


def migrate_if_needed(project_dir: Path, locks: _MigrationLocks | None = None) -> int:
    """Fold dismissed.json into actions.jsonl exactly once. Returns count migrated.

    *locks* overrides the process-wide lock table (``_DEFAULT_LOCKS``).
    """
    marker = project_dir / MIGRATION_MARKER
    if marker.exists():
        return 0

    dismissed_json = project_dir / "dismissed.json"
    if not dismissed_json.is_file():
        # Fresh install (no legacy data). Nothing to fold and nothing to mark;
        # the two cheap exists() checks above keep this path negligible.
        return 0

    with (locks or _DEFAULT_LOCKS).for_project(project_dir):
        if marker.exists():  # another thread won the race
            return 0

        try:
            entries = json.loads(dismissed_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _logger.warning("Could not read %s during migration; skipping", dismissed_json)
            return 0
        if not isinstance(entries, list):
            # Malformed legacy file: nothing to fold, but mark so we never retry.
            _write_marker(marker)
            return 0

        writer = ActionLogWriter(project_dir)
        count = _fold_legacy_entries(writer, entries)

        # Mark last: a crash mid-fold leaves the marker absent so the next call
        # re-folds. Re-folding only appends duplicate FindingDismissed events,
        # which are idempotent for the replayed dismissed set.
        _write_marker(marker)
        _logger.info(
            "Migrated %d entries from dismissed.json to actions.jsonl in %s",
            count,
            project_dir,
        )
        return count


def _write_marker(marker: Path) -> None:
    try:
        marker.write_text("", encoding="utf-8")
    except OSError:
        _logger.warning("Could not write migration marker %s", marker)
