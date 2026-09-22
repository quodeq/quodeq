"""assistant/adapters/_stream.py reads the same Claude/Copilot stream-json
wire format core.stream.events parses server-side; both compare event
"type" values, so _stream.py imports the EVENT_TYPE_* constants from
core.stream.events rather than retyping "assistant"/"result"/etc."""
from __future__ import annotations

from quodeq.core.stream.events import (
    EVENT_TYPE_ASSISTANT, EVENT_TYPE_ASSISTANT_MESSAGE, EVENT_TYPE_ITEM_COMPLETED,
    EVENT_TYPE_RESULT, EVENT_TYPE_TOOL_EXECUTION_START,
)


def test_stream_adapter_imports_the_shared_event_type_constants():
    from quodeq.assistant.adapters import _stream

    assert _stream.EVENT_TYPE_ASSISTANT is EVENT_TYPE_ASSISTANT
    assert _stream.EVENT_TYPE_ASSISTANT_MESSAGE is EVENT_TYPE_ASSISTANT_MESSAGE
    assert _stream.EVENT_TYPE_RESULT is EVENT_TYPE_RESULT
    assert _stream.EVENT_TYPE_ITEM_COMPLETED is EVENT_TYPE_ITEM_COMPLETED
    assert _stream.EVENT_TYPE_TOOL_EXECUTION_START is EVENT_TYPE_TOOL_EXECUTION_START
