"""Every tools/call reply is one text block; errors add ``isError`` and successes omit it."""
from __future__ import annotations

from unittest.mock import MagicMock

from quodeq.analysis.mcp.handlers import handle_tools_call


def test_an_error_reply_carries_is_error_after_the_content():
    result = handle_tools_call(request_id=7, params={"name": "nope"}, router=MagicMock())
    assert result["id"] == 7
    assert result["result"] == {
        "content": [{"type": "text", "text": "Unknown tool: nope"}], "isError": True,
    }
    assert list(result["result"]) == ["content", "isError"]


def test_a_success_reply_has_no_is_error_key():
    router = MagicMock()
    result = handle_tools_call(
        request_id=8, params={"name": "mark_file_done", "arguments": {"file": "a.py", "status": "ok"}},
        router=router,
    )
    assert result["result"] == {"content": [{"type": "text", "text": "marked"}]}


def test_a_router_refusal_is_an_error_reply_with_its_message():
    router = MagicMock()
    router.mark_file_done.side_effect = ValueError("bad status")
    result = handle_tools_call(
        request_id=9, params={"name": "mark_file_done", "arguments": {"file": "a.py", "status": "x"}},
        router=router,
    )
    assert result["result"] == {"content": [{"type": "text", "text": "bad status"}], "isError": True}
