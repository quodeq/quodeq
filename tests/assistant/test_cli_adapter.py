"""CLI adapter streaming: token frames, echo suppression, tool-use frames, codex items."""
import pytest

from quodeq.assistant.adapters.cli import run_cli_turn

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session


def test_streams_tokens_and_captures_session_id(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "system", "session_id": "claude-uuid-1"}',
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}',
        '{"type": "result", "result": "Hello", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Hello"
    assert {"type": "token", "text": "Hello"} in frames
    assert repo.get_session("s1")["cli_session_id"] == "claude-uuid-1"


def test_result_echo_of_streamed_text_is_not_emitted_twice(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}',
        '{"type": "result", "result": "Hello", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Hello"
    token_frames = [f for f in frames if f == {"type": "token", "text": "Hello"}]
    assert len(token_frames) == 1


def test_result_only_text_is_still_emitted(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "result", "result": "Hi"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Hi"
    assert {"type": "token", "text": "Hi"} in frames


def test_result_with_differing_text_is_emitted(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 1 done"}]}}',
        '{"type": "result", "result": "Final answer: X", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    token_texts = [f["text"] for f in frames if f["type"] == "token"]
    assert token_texts == ["Step 1 done", "Final answer: X"]
    assert text == "Final answer: X"


def _delta(text):
    return ('{"type": "stream_event", "event": {"type": "content_block_delta", '
            '"index": 0, "delta": {"type": "text_delta", "text": "%s"}}}' % text)


def test_claude_partial_deltas_stream_and_message_echo_is_suppressed(tmp_path):
    # With --include-partial-messages the CLI streams text_delta chunks, then
    # echoes the complete message as an `assistant` event, then again as
    # `result`. The chunks must be emitted as they arrive; neither echo may
    # repeat text already streamed.
    repo = _repo(tmp_path)
    lines = [
        _delta("Hel"),
        _delta("lo"),
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}',
        '{"type": "result", "result": "Hello", "session_id": "claude-uuid-1"}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Hello"
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Hel", "lo"]


def test_claude_deltas_reset_per_message_across_tool_use(tmp_path):
    # A tool-use turn carries several assistant messages, each streamed via its
    # own deltas. Echo suppression must reset per message, and the final
    # `result` (which repeats only the LAST message) must stay suppressed.
    repo = _repo(tmp_path)
    lines = [
        _delta("Checking."),
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Checking."}, '
        '{"type": "tool_use", "name": "get_scores", "input": {}}]}}',
        _delta("Done"),
        _delta("."),
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}}',
        '{"type": "result", "result": "Done."}',
    ]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Done."
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Checking.", "Done", "."]
    assert any(f["type"] == "tool_call" and f["name"] == "get_scores" for f in frames)


def test_message_echo_differing_from_deltas_is_still_emitted(tmp_path):
    # Same content-not-presence gate as the result echo: if the complete
    # message DIFFERS from what the deltas streamed, it must not be swallowed.
    repo = _repo(tmp_path)
    lines = [
        _delta("Hel"),
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}',
        '{"type": "result", "result": "Hello world"}',
    ]
    frames = []
    run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Hel", "Hello world"]


def test_partial_deltas_without_message_completion_count_as_output(tmp_path):
    # A killed/stopped turn ends mid-message: deltas streamed but no complete
    # `assistant` echo ever arrives. The streamed text is the answer the user
    # saw, so it must survive into the returned/partial text.
    repo = _repo(tmp_path)
    lines = [_delta("Par"), _delta("tial")]
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "hi"}],
        config=_config(tmp_path),
        session=_session(repo, emit=frames.append,
                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "Partial"
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Par", "tial"]


def test_tool_use_emits_frame(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "get_scores", "input": {}}]}}',
        '{"type": "result", "result": "done"}',
    ]
    frames = []
    run_cli_turn(messages=[{"role": "user", "content": "scores?"}], config=_config(tmp_path),
                 session=_session(repo, emit=frames.append,
                                  spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert any(f["type"] == "tool_call" and f["name"] == "get_scores" for f in frames)


def test_codex_multiple_agent_messages_are_joined(tmp_path):
    # Codex emits several agent_message items and no `result` echo, so the answer
    # is the concatenation of the chunks, not just the last one.
    repo = _repo(tmp_path)
    lines = [
        '{"type": "item.completed", "item": {"type": "agent_message", "text": "First part."}}',
        '{"type": "item.completed", "item": {"type": "agent_message", "text": "Second part."}}',
        '{"type": "turn.completed", "usage": {}}',
    ]
    frames = []
    text = run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                        session=_session(repo, emit=frames.append,
                                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "First part.\n\nSecond part."
    assert [f["text"] for f in frames if f["type"] == "token"] == ["First part.", "Second part."]


def test_codex_partial_text_then_turn_failed_raises(tmp_path):
    # A turn that streams a partial answer then fails must surface the failure,
    # not return the truncated partial as if it were the final answer.
    repo = _repo(tmp_path)
    lines = [
        '{"type": "item.completed", "item": {"type": "agent_message", "text": "Here is a partial"}}',
        '{"type": "turn.failed", "error": {"message": "token limit exceeded"}}',
    ]
    with pytest.raises(RuntimeError, match="token limit exceeded"):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}], config=_config(tmp_path),
                     session=_session(repo, spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))


def test_codex_mcp_tool_call_emits_single_frame(tmp_path):
    repo = _repo(tmp_path)
    lines = [
        '{"type": "item.started", "item": {"type": "mcp_tool_call", "server": "quodeq-assistant", "tool": "get_context", "arguments": {}, "status": "in_progress"}}',
        '{"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "get_context", "arguments": {}, "status": "completed"}}',
        '{"type": "item.completed", "item": {"type": "agent_message", "text": "The scope is X."}}',
        '{"type": "turn.completed", "usage": {}}',
    ]
    frames = []
    text = run_cli_turn(messages=[{"role": "user", "content": "scope?"}], config=_config(tmp_path),
                        session=_session(repo, emit=frames.append,
                                         spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert text == "The scope is X."
    assert [f for f in frames if f["type"] == "tool_call"] == [
        {"type": "tool_call", "name": "get_context"}]
