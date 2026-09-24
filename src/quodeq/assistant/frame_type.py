"""The assistant SSE frame's type vocabulary."""
from __future__ import annotations

from enum import StrEnum


class FrameType(StrEnum):
    """The ``type`` of one assistant stream frame; the UI mirror is ``ui/src/vocab/frameType.js``.

    A different domain from the run/job vocabularies even where a spelling
    coincides (``error``, ``done``).
    """

    TOKEN = "token"
    TOOL_CALL = "tool_call"
    ACTION_DRAFT = "action_draft"
    WARNING = "warning"
    ERROR = "error"
    STOPPED = "stopped"
    DONE = "done"
    HEARTBEAT = "heartbeat"
