"""Append-only log of post-scan user actions, project-scoped.

Mirrors EventLogWriter but writes to project_dir/actions.jsonl. This log is
read by the projection engine to apply user actions (dismissals, etc.) onto
the per-run state stores.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Iterator

from quodeq.core.events.models import EVENT_MODEL_MAP, BaseEvent, EventType
from quodeq.data.events.codec import event_from_dict
from quodeq.data.jsonl_append import JsonlAppendMixin
from quodeq.data.locking import get_file_lock


_logger = logging.getLogger(__name__)

ACTIONS_LOG_FILENAME = "actions.jsonl"


class ActionLogWriter(JsonlAppendMixin):
    """Thread-safe append-only writer for project_dir/actions.jsonl."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self.log_path = project_dir / ACTIONS_LOG_FILENAME
        project_dir.mkdir(parents=True, exist_ok=True)
        self._lock = get_file_lock()
        self._logger = _logger

    def _emit_what(self, event: BaseEvent) -> str:
        return str(event.event_type)


def _timestamp_key(line: str) -> tuple[int, str]:
    """Sort key for a raw actions-log JSON line: timestamped lines first,
    ordered by timestamp; anything unparseable or missing a timestamp
    sorts last, in original order."""
    try:
        ts = json.loads(line).get("timestamp")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return (1, "")
    if not ts:
        return (1, "")
    return (0, str(ts))


def merge_action_log_files(dst: Path, srcs: Iterable[Path]) -> None:
    """Union-merge *srcs* actions.jsonl files into *dst*, deduped and sorted.

    Missing sources are skipped. Nothing is written when the union is empty
    (a caller staging a project with no actions log at all must not create
    one). Raises ``ValueError`` (a plain ``UnicodeDecodeError``) if any
    source is not valid UTF-8 -- callers that need a user-facing error
    (rather than a raw decode error) catch this themselves.
    """
    seen: set[str] = set()
    lines: list[str] = []
    for source in srcs:
        if not source.exists():
            continue
        for raw in source.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    if not lines:
        return
    lines.sort(key=_timestamp_key)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_action_events(project_dir: Path, *, from_offset: int = 0) -> Iterator[BaseEvent]:
    """Yield typed events from project_dir/actions.jsonl. Skips malformed lines.

    ``from_offset`` resumes reading at that byte position. The log is
    append-only (one JSON line per event, flushed under a file lock), so any
    previously recorded file size is a valid line boundary.
    """
    log_path = project_dir / ACTIONS_LOG_FILENAME
    if not log_path.is_file():
        return
    with open(log_path, encoding="utf-8") as f:
        if from_offset > 0:
            # int-seek on a text-mode file is only formally valid for offsets
            # returned by f.tell(); it's exact here because from_offset is
            # always a previously recorded file size, which lands on a UTF-8
            # line boundary in this append-only log.
            f.seek(from_offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                event_type = EventType(data["event_type"])
                model_cls = EVENT_MODEL_MAP[event_type]
                yield event_from_dict(model_cls, data)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                _logger.warning("Skipping malformed actions.jsonl line: %s", e)
                continue
