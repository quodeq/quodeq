import pytest

from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.assistant.tools import ToolContext
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def setup(tmp_path):
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama", model="m")
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    return repo, ctx


def _request(text="hello", ui_state=None):
    return TurnRequest(session_id="s1", text=text, ui_state=ui_state,
                       api_base="http://x/v1", api_key=None,
                       provider="ollama", model="m")


def test_turn_persists_messages_and_emits_done(setup):
    repo, ctx = setup

    def fake_turn(*, messages, config, registry, emit, **_):
        assert messages[0]["role"] == "system"
        assert messages[-1] == {"role": "user", "content": "hello"}
        emit({"type": "token", "text": "hi"})
        return "hi"

    run_turn(_request(), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    msgs = repo.list_messages("s1")
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "hello"), ("assistant", "hi")]
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1] == {"type": "done"}


def test_ui_state_prepended_to_user_message(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, **_):
        seen["user"] = messages[-1]["content"]
        return "ok"

    run_turn(_request(ui_state={"activeTab": "standards"}), repository=repo,
             tool_ctx=ctx, turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    assert seen["user"].startswith("[ui-state]")


def test_skill_prefix_injects_instructions(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, **_):
        seen["system"] = messages[0]["content"]
        seen["user"] = messages[-1]["content"]
        return "ok"

    run_turn(_request(text="/create-standard RFC7807 errors"), repository=repo,
             tool_ctx=ctx, turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    assert "Active skill: create-standard" in seen["system"]
    assert seen["user"] == "RFC7807 errors"


def test_unknown_skill_emits_error_without_model_call(setup):
    repo, ctx = setup

    def fake_turn(**_):
        raise AssertionError("model must not be called")

    run_turn(_request(text="/nope do it"), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "error"


def test_turn_exception_becomes_error_frame(setup):
    repo, ctx = setup

    def fake_turn(**_):
        raise RuntimeError("connection refused")

    run_turn(_request(), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "error"
    assert "connection refused" in frames[-1]["message"]


def test_history_replayed_on_second_turn(setup):
    repo, ctx = setup
    repo.add_message("s1", "user", "first")
    repo.add_message("s1", "assistant", "first answer")
    seen = {}

    def fake_turn(*, messages, **_):
        seen["messages"] = messages
        return "second answer"

    run_turn(_request(text="second"), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    roles = [m["role"] for m in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
