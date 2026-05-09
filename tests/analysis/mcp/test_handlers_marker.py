from __future__ import annotations
from unittest.mock import MagicMock

from quodeq.analysis.mcp.handlers import handle_tools_list, handle_tools_call


class TestToolsListIncludesMarker:
    def test_marker_listed(self):
        result = handle_tools_list(request_id=1, has_queue=True)
        names = {t["name"] for t in result["result"]["tools"]}
        assert "mark_file_done" in names

    def test_marker_listed_even_without_queue(self):
        # The marker tool is independent of the queue — single-agent paths
        # still want to mark per-file completion.
        result = handle_tools_list(request_id=1, has_queue=False)
        names = {t["name"] for t in result["result"]["tools"]}
        assert "mark_file_done" in names


class TestToolsCallDispatchesMarker:
    def test_ok_marker_routed_to_router(self):
        router = MagicMock()
        handle_tools_call(
            request_id=1,
            params={"name": "mark_file_done", "arguments": {"file": "a.py", "status": "ok"}},
            router=router,
        )
        router.mark_file_done.assert_called_once_with(file="a.py", status="ok", reason=None)

    def test_error_marker_with_reason_routed(self):
        router = MagicMock()
        handle_tools_call(
            request_id=1,
            params={"name": "mark_file_done", "arguments": {"file": "b.py", "status": "error", "reason": "token_limit"}},
            router=router,
        )
        router.mark_file_done.assert_called_once_with(file="b.py", status="error", reason="token_limit")

    def test_invalid_args_returns_error_response(self):
        router = MagicMock()
        router.mark_file_done.side_effect = ValueError("bogus")
        result = handle_tools_call(
            request_id=1,
            params={"name": "mark_file_done", "arguments": {"file": "b.py", "status": "bogus"}},
            router=router,
        )
        assert result["result"].get("isError") is True
