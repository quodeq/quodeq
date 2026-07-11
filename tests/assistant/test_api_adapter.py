import json
from types import SimpleNamespace

from quodeq.assistant.adapters._api import ApiTurnConfig, run_api_turn
from quodeq.assistant.tools._registry import ToolRegistry, ToolSpec


def _delta(content=None, tool_calls=None, finish=None):
    d = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=d, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


def _tool_call_delta(index, call_id=None, name=None, args=""):
    fn = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(index=index, id=call_id, function=fn)


class FakeClient:
    """Yields scripted streams; one script (list of chunks) per create() call."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._scripts.pop(0))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _registry():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        "get_scores", "scores", {"type": "object", "properties": {}},
        lambda: {"security": {"score": 61.5, "grade": "C"}}))
    return reg


def _config(native=True):
    return ApiTurnConfig(api_base="http://x/v1", api_key=None,
                         model="m", native_tools=native)


def test_plain_streamed_answer():
    client = FakeClient([[_delta("Hel"), _delta("lo"), _delta(finish="stop")]])
    frames = []
    text = run_api_turn(messages=[{"role": "user", "content": "hi"}],
                        config=_config(), registry=_registry(),
                        emit=frames.append, client_factory=lambda c: client)
    assert text == "Hello"
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Hel", "lo"]
    assert client.calls[0]["stream"] is True
    assert client.calls[0]["tools"]  # native tools passed


def test_native_tool_loop_dispatches_and_feeds_result_back():
    turn1 = [
        _delta(tool_calls=[_tool_call_delta(0, "c1", "get_scores", "")]),
        _delta(tool_calls=[_tool_call_delta(0, None, None, "{}")]),
        _delta(finish="tool_calls"),
    ]
    turn2 = [_delta("Grade is C"), _delta(finish="stop")]
    client = FakeClient([turn1, turn2])
    frames = []
    text = run_api_turn(messages=[{"role": "user", "content": "score?"}],
                        config=_config(), registry=_registry(),
                        emit=frames.append, client_factory=lambda c: client)
    assert text == "Grade is C"
    tool_frames = [f for f in frames if f["type"] == "tool_call"]
    assert tool_frames == [{"type": "tool_call", "name": "get_scores", "ok": True}]
    # second call got the assistant tool_calls msg + fenced tool result
    msgs = client.calls[1]["messages"]
    assert msgs[-2]["role"] == "assistant"
    assert msgs[-1]["role"] == "tool"
    assert "UNTRUSTED DATA" in msgs[-1]["content"]


def test_fallback_mode_uses_prompted_json_and_no_tools_param():
    turn1 = [_delta('{"tool_call": {"name": "get_scores", "arguments": {}}}'),
             _delta(finish="stop")]
    turn2 = [_delta("C grade"), _delta(finish="stop")]
    client = FakeClient([turn1, turn2])
    text = run_api_turn(messages=[{"role": "user", "content": "score?"}],
                        config=_config(native=False), registry=_registry(),
                        emit=lambda f: None, client_factory=lambda c: client)
    assert text == "C grade"
    assert "tools" not in client.calls[0]
    assert "tool_call" in client.calls[0]["messages"][0]["content"]  # contract in system


def test_tool_call_frame_carries_args_summary():
    turn1 = [_delta('{"tool_call": {"name": "get_scores", "arguments": {"dimension": "security"}}}'),
             _delta(finish="stop")]
    turn2 = [_delta("C grade"), _delta(finish="stop")]
    client = FakeClient([turn1, turn2])
    frames = []
    run_api_turn(messages=[{"role": "user", "content": "score?"}],
                 config=_config(native=False), registry=_registry(),
                 emit=frames.append, client_factory=lambda c: client)
    tool_frames = [f for f in frames if f["type"] == "tool_call"]
    assert tool_frames and tool_frames[0]["argsSummary"].startswith('{"')


def test_iteration_cap_ends_turn():
    looping = [
        _delta(tool_calls=[_tool_call_delta(0, "c1", "get_scores", "{}")]),
        _delta(finish="tool_calls"),
    ]
    client = FakeClient([list(looping) for _ in range(10)])
    text = run_api_turn(messages=[{"role": "user", "content": "x"}],
                        config=_config(), registry=_registry(),
                        emit=lambda f: None, client_factory=lambda c: client)
    assert "tool iteration limit" in text
    assert len(client.calls) == 6  # MAX_TOOL_ITERATIONS


def test_iteration_cap_is_config_driven():
    looping = [
        _delta(tool_calls=[_tool_call_delta(0, "c1", "get_scores", "{}")]),
        _delta(finish="tool_calls"),
    ]
    client = FakeClient([list(looping) for _ in range(10)])
    config = ApiTurnConfig(api_base="http://x", api_key=None, model="m",
                           native_tools=True, max_tool_iterations=2)
    run_api_turn(messages=[{"role": "user", "content": "x"}],
                 config=config, registry=_registry(),
                 emit=lambda f: None, client_factory=lambda c: client)
    assert len(client.calls) == 2


def test_extra_body_disables_thinking_for_local_and_sets_ctx(monkeypatch):
    from quodeq.assistant.adapters._api import ApiTurnConfig, _extra_body
    monkeypatch.setenv("QUODEQ_CONTEXT_SIZE", "32768")
    local = ApiTurnConfig(api_base="http://localhost:11434/v1", api_key=None, model="m", native_tools=True)
    body = _extra_body(local)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["num_ctx"] == 32768
    assert "reasoning_effort" not in body


def test_extra_body_openai_uses_reasoning_effort(monkeypatch):
    from quodeq.assistant.adapters._api import ApiTurnConfig, _extra_body
    monkeypatch.delenv("QUODEQ_CONTEXT_SIZE", raising=False)
    cloud = ApiTurnConfig(api_base="https://api.openai.com/v1", api_key="k", model="gpt", native_tools=True)
    body = _extra_body(cloud)
    assert body["reasoning_effort"] == "none"
    assert "chat_template_kwargs" not in body
    assert "num_ctx" not in body


# ---- stop-turn cancellation -------------------------------------------------

class ClosableFakeClient(FakeClient):
    def __init__(self, scripts):
        super().__init__(scripts)
        self.closed = False

    def close(self):
        self.closed = True


def test_cancel_mid_stream_raises_turn_cancelled_with_partial():
    import pytest
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    token = CancelToken()
    client = ClosableFakeClient([[_delta("Hel"), _delta("lo"), _delta(finish="stop")]])
    frames = []

    def emit(frame):
        frames.append(frame)
        token.cancel()  # user hits Stop after the first streamed token

    with pytest.raises(TurnCancelled) as exc:
        run_api_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(), registry=_registry(),
                     emit=emit, client_factory=lambda c: client, cancel=token)
    assert exc.value.partial == "Hel"
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Hel"]


def test_precancelled_closes_client_and_skips_request():
    import pytest
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    token = CancelToken()
    token.cancel()
    client = ClosableFakeClient([])

    with pytest.raises(TurnCancelled) as exc:
        run_api_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(), registry=_registry(),
                     emit=lambda f: None, client_factory=lambda c: client, cancel=token)
    assert exc.value.partial == ""
    assert client.calls == []      # never asked the model anything
    assert client.closed is True   # kill hook ran immediately


def test_stream_error_while_cancelled_is_turn_cancelled():
    # cancel() closes the HTTP client to interrupt a stalled stream; the read
    # then raises in the turn thread. That exception is the cancellation
    # succeeding, not a turn failure.
    import pytest
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    token = CancelToken()

    def dying_stream():
        yield _delta("Hel")
        raise RuntimeError("connection closed mid-read")

    client = ClosableFakeClient([dying_stream()])

    def emit(frame):
        token.cancel()

    with pytest.raises(TurnCancelled) as exc:
        run_api_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(), registry=_registry(),
                     emit=emit, client_factory=lambda c: client, cancel=token)
    assert exc.value.partial == "Hel"


def test_stream_error_without_cancel_still_raises():
    import pytest

    def dying_stream():
        yield _delta("Hel")
        raise RuntimeError("connection dropped")

    client = ClosableFakeClient([dying_stream()])
    with pytest.raises(RuntimeError, match="connection dropped"):
        run_api_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(), registry=_registry(),
                     emit=lambda f: None, client_factory=lambda c: client)


def test_cancel_interrupts_a_stalled_stream_read():
    # Live-repro regression: cancel() while the turn thread is BLOCKED inside
    # the chunk read (model stalled / connection wedged). Closing the client
    # from another thread does not reliably wake a blocked socket read, so the
    # turn must not depend on another chunk arriving to notice the cancel.
    import threading
    import time
    import pytest
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    token = CancelToken()
    release = threading.Event()

    def stalled_stream():
        yield _delta("Hel")
        release.wait(timeout=30)  # blocks like a dead connection: no data, no EOF
        yield _delta("lo")

    client = ClosableFakeClient([stalled_stream()])
    outcome = {}

    def _turn():
        try:
            run_api_turn(messages=[{"role": "user", "content": "hi"}],
                         config=_config(), registry=_registry(),
                         emit=lambda f: None, client_factory=lambda c: client,
                         cancel=token)
            outcome["result"] = "returned"
        except TurnCancelled as exc:
            outcome["result"] = "cancelled"
            outcome["partial"] = exc.partial

    t = threading.Thread(target=_turn, daemon=True)
    t.start()
    time.sleep(0.3)   # let the turn consume "Hel" and block in the stalled read
    token.cancel()
    t.join(timeout=3)
    release.set()     # unblock the abandoned reader so the test process exits clean
    if t.is_alive():
        pytest.fail("turn thread still blocked 3s after cancel()")
    assert outcome["result"] == "cancelled"
    assert outcome["partial"] == "Hel"
