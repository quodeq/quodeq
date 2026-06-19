from __future__ import annotations
from unittest.mock import MagicMock

from quodeq.analysis.mcp.handlers import handle_tools_list, handle_tools_call


# ---------------------------------------------------------------------------
# #207 — null 'arguments' in params must be treated as {} (not raise TypeError)
# ---------------------------------------------------------------------------

class TestToolsCallNullArguments:
    def test_null_arguments_for_report_finding_does_not_raise(self) -> None:
        """params.arguments = null must not crash handle_tools_call."""
        router = MagicMock()
        router.receive.return_value = ("ok", False)
        # Simulate a JSON-RPC caller that sends {"arguments": null}
        result = handle_tools_call(
            request_id=1,
            params={"name": "report_finding", "arguments": None},
            router=router,
        )
        # Should return a valid ok-response (not a 500/AttributeError)
        assert "result" in result
        router.receive.assert_called_once_with({})

    def test_missing_arguments_key_still_works(self) -> None:
        router = MagicMock()
        router.receive.return_value = ("ok", False)
        result = handle_tools_call(
            request_id=2,
            params={"name": "report_finding"},
            router=router,
        )
        assert "result" in result
        router.receive.assert_called_once_with({})


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

    def test_router_value_error_returns_error_response(self):
        router = MagicMock()
        router.mark_file_done.side_effect = ValueError("status must be ok or error")
        result = handle_tools_call(
            request_id=1,
            params={"name": "mark_file_done", "arguments": {"file": "b.py", "status": "bogus"}},
            router=router,
        )
        assert result["result"].get("isError") is True
        router.mark_file_done.assert_called_once()

    def test_non_string_args_short_circuit_without_calling_router(self):
        router = MagicMock()
        result = handle_tools_call(
            request_id=1,
            params={"name": "mark_file_done", "arguments": {"file": 123, "status": "ok"}},
            router=router,
        )
        assert result["result"].get("isError") is True
        router.mark_file_done.assert_not_called()
