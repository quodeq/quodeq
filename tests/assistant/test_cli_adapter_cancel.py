"""CLI adapter stop-turn cancellation."""
import pytest

from quodeq.assistant.adapters.cli import run_cli_turn

from ._cli_adapter_helpers import FakeProc, _config, _repo, _session


# ---- stop-turn cancellation -------------------------------------------------

def test_cancel_mid_turn_raises_turn_cancelled_with_partial(tmp_path):
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    repo = _repo(tmp_path)
    token = CancelToken()
    lines = [
        '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hel"}]}}',
        '{"type": "result", "result": "Hello"}',
    ]

    def emit(frame):
        token.cancel()  # user hits Stop right after the first streamed token

    with pytest.raises(TurnCancelled) as exc:
        run_cli_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(tmp_path),
                     session=_session(repo, emit=emit, cancel=token,
                                      spawn_fn=lambda argv, *, cwd, env: FakeProc(lines)))
    assert exc.value.partial == "Hello"


def test_cancel_kills_the_cli_process(tmp_path):
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    repo = _repo(tmp_path)
    token = CancelToken()
    proc = FakeProc(['{"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}'])

    def emit(frame):
        token.cancel()

    with pytest.raises(TurnCancelled):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(tmp_path),
                     session=_session(repo, emit=emit, cancel=token,
                                      spawn_fn=lambda argv, *, cwd, env: proc))
    # the token's kill hook (not the exit-path cleanup: poll() reports the
    # scripted proc as already exited) must have killed the process tree
    assert proc.killed is True


def test_precancelled_token_spawns_nothing(tmp_path):
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    repo = _repo(tmp_path)
    token = CancelToken()
    token.cancel()
    spawns = []

    def spawn(argv, *, cwd, env):
        spawns.append(argv)
        return FakeProc([])

    with pytest.raises(TurnCancelled):
        run_cli_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(tmp_path),
                     session=_session(repo, cancel=token, spawn_fn=spawn))
    assert spawns == []


def test_cancelled_turn_never_rebuilds(tmp_path):
    # A cancelled resumed turn that produced no text must raise TurnCancelled,
    # NOT trigger the empty-output session rebuild (which would rerun the whole
    # turn against the model the user just stopped).
    from quodeq.assistant.cancel import CancelToken, TurnCancelled
    repo = _repo(tmp_path)
    token = CancelToken()
    spawns = []
    tool_line = ('{"type": "assistant", "message": {"content": '
                 '[{"type": "tool_use", "name": "get_scores", "input": {}}]}}')

    def spawn(argv, *, cwd, env):
        spawns.append(argv)
        return FakeProc([tool_line])

    def emit(frame):
        token.cancel()  # stop lands during the tool call, before any text

    with pytest.raises(TurnCancelled) as exc:
        run_cli_turn(messages=[{"role": "user", "content": "hi"}],
                     config=_config(tmp_path),
                     session=_session(repo, prior_session_id="old-sid", emit=emit,
                                      cancel=token, spawn_fn=spawn))
    assert len(spawns) == 1
    assert exc.value.partial == ""
