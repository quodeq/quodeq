"""Chat message roles shared by the orchestrator and the API/CLI turn adapters."""
from __future__ import annotations

from enum import StrEnum


class MessageRole(StrEnum):
    """A chat message's role in the OpenAI/Claude-style transcript.

    data/sqlite/_assistant_schema.py's ``messages.role`` CHECK constraint
    covers USER, ASSISTANT and TOOL (SQL text can't reference this name).
    SYSTEM is used only for the composed turn payload; it is never
    persisted to that table.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
