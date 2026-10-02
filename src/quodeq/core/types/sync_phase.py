"""The sync-job vocabulary: which job, and which phase it is in.

Home module for these words (tools/check_vocab_literals.py); every other
module branches on the members, never on the strings. Wire values of
GET /api/shared/status.
"""
from __future__ import annotations

from enum import StrEnum


class SyncKind(StrEnum):
    """Which sync job ran."""

    CONNECT = "connect"
    REFRESH = "refresh"
    PULL = "pull"


class SyncPhase(StrEnum):
    """Where a sync job is in its life."""

    CONNECTING = "connecting"
    DOWNLOADING = "downloading"
    READING = "reading"
    DONE = "done"
    ERROR = "error"
