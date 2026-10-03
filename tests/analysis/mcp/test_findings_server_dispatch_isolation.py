"""main()'s per-message dispatch is a run_isolated boundary.

Split out of test_findings_server.py (300-line file guard). A handler bug
(an exception outside router.py's narrowed types) must not kill the whole
MCP subprocess: the failing message gets a JSON-RPC error response (when it
carried a request id) and the loop keeps serving the next message.
"""
from __future__ import annotations

import json

import quodeq.analysis.mcp.findings_server as findings_server_module
from quodeq.analysis.mcp.findings_server import main
from quodeq.analysis.mcp.args import ServerArgs


def test_dispatch_failure_is_isolated_per_message_and_still_serves_the_next(
    capsys, monkeypatch, tmp_path,
):
    """The per-message dispatch in main()'s stdio loop is a run_isolated
    boundary (one iteration of the event loop): a handler bug (AttributeError
    -- not one of router.py's narrowed exception types) must not kill the
    whole subprocess. The failing message gets a JSON-RPC error response
    (it carried a request id) and the next message is still dispatched."""
    sa = ServerArgs()
    findings_path = tmp_path / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    sa.findings_file = str(findings_path)

    monkeypatch.setattr(findings_server_module, "parse_args", lambda: sa)
    monkeypatch.setattr(findings_server_module, "_build_compiled_context", lambda _sa: object())
    monkeypatch.setattr(findings_server_module, "_build_router", lambda *a, **kw: object())

    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "boom"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        None,
    ]
    monkeypatch.setattr(findings_server_module, "read_message", lambda: messages.pop(0))

    calls: list[object] = []

    def fake_dispatch(msg, _router, _queue, _agent_id):
        calls.append(msg["id"])
        if msg["id"] == 1:
            raise AttributeError("handler bug")

    monkeypatch.setattr(findings_server_module, "_dispatch", fake_dispatch)

    main()  # must not raise -- the whole point of this test

    # Both messages reached dispatch: the loop continued past the failure.
    assert calls == [1, 2]

    out = capsys.readouterr().out
    responses = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert len(responses) == 1
    assert responses[0]["id"] == 1
    assert responses[0]["error"]["code"] == -32603
    assert "AttributeError" in responses[0]["error"]["message"]


def test_dispatch_failure_for_a_notification_sends_no_response(monkeypatch, tmp_path, capsys):
    """A JSON-RPC notification (no ``id``) that fails must not get a
    response -- there is no request to answer, per the JSON-RPC 2.0 spec."""
    sa = ServerArgs()
    findings_path = tmp_path / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    sa.findings_file = str(findings_path)

    monkeypatch.setattr(findings_server_module, "parse_args", lambda: sa)
    monkeypatch.setattr(findings_server_module, "_build_compiled_context", lambda _sa: object())
    monkeypatch.setattr(findings_server_module, "_build_router", lambda *a, **kw: object())

    messages = [{"jsonrpc": "2.0", "method": "notifications/boom"}, None]
    monkeypatch.setattr(findings_server_module, "read_message", lambda: messages.pop(0))

    def fake_dispatch(_msg, _router, _queue, _agent_id):
        raise AttributeError("handler bug")

    monkeypatch.setattr(findings_server_module, "_dispatch", fake_dispatch)

    main()  # must not raise

    assert capsys.readouterr().out == ""
