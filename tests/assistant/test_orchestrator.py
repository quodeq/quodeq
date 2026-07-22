import pytest

from quodeq.assistant.orchestrator import TurnRequest, _mcp_server_args, run_turn
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


def _request(text="hello", ui_state=None, **kw):
    return TurnRequest(session_id="s1", text=text, ui_state=ui_state,
                       api_base="http://x/v1", api_key=None,
                       provider="ollama", model="m", **kw)


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


def test_run_turn_dispatches_cli_provider(setup, monkeypatch):
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})
    called = {}

    def fake_cli_turn(**kwargs):
        called["hit"] = True
        return "cli answer"

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", fake_cli_turn)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="", api_key=None,
                      provider="claude", model="sonnet")
    run_turn(req, repository=repo, tool_ctx=ctx)
    assert called.get("hit") is True
    msgs = repo.list_messages("s1")
    assert msgs[-1]["content"] == "cli answer"


def test_run_turn_cli_empty_output_emits_error(setup, monkeypatch):
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})

    def boom(**kwargs):
        raise RuntimeError("CLI produced no output")

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", boom)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="", api_key=None,
                      provider="claude", model="sonnet")
    run_turn(req, repository=repo, tool_ctx=ctx)
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "error"
    assert "no output" in frames[-1]["message"]


def test_mcp_server_args_includes_run_and_repo(setup, tmp_path):
    repo, _ctx = setup
    ctx = ToolContext(
        repository=repo, session_id="s1",
        run_dir=tmp_path / "run", repo_root=tmp_path / "repo",
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    args = _mcp_server_args(_request(), ctx)
    assert "--run-dir" in args
    assert args[args.index("--run-dir") + 1] == str(tmp_path / "run")
    assert "--repo-root" in args
    assert args[args.index("--repo-root") + 1] == str(tmp_path / "repo")


def test_mcp_server_args_omits_run_and_repo_when_unset(setup):
    repo, ctx = setup  # fixture ctx has run_dir=None, repo_root=None
    args = _mcp_server_args(_request(), ctx)
    assert "--run-dir" not in args
    assert "--repo-root" not in args


def test_mcp_server_args_includes_project_id_and_reports_dir(setup, tmp_path):
    repo, _ctx = setup
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="selectives", reports_dir=tmp_path / "reports",
    )
    args = _mcp_server_args(_request(), ctx)
    assert args[args.index("--project-id") + 1] == "selectives"
    assert args[args.index("--reports-dir") + 1] == str(tmp_path / "reports")


def test_mcp_server_args_omits_project_scope_when_unset(setup):
    repo, ctx = setup  # fixture ctx has project_id=None, reports_dir=None
    args = _mcp_server_args(_request(), ctx)
    assert "--project-id" not in args
    assert "--reports-dir" not in args


def test_web_enabled_registers_web_tools_for_local_provider(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, registry, emit, **_):
        seen["names"] = registry.names()
        seen["system"] = messages[0]["content"]
        return "ok"

    run_turn(_request(web_enabled=True), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    assert "search_web" in seen["names"] and "fetch_url" in seen["names"]
    assert "# Web access" in seen["system"]


def test_web_tools_absent_by_default(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, registry, emit, **_):
        seen["names"] = registry.names()
        seen["system"] = messages[0]["content"]
        return "ok"

    run_turn(_request(), repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    assert "search_web" not in seen["names"] and "fetch_url" not in seen["names"]
    assert "# Web access" not in seen["system"]


def test_web_enabled_ignored_for_cloud_api_provider(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, registry, emit, **_):
        seen["names"] = registry.names()
        return "ok"

    req = TurnRequest(session_id="s1", text="hi", ui_state=None,
                      api_base="https://openrouter.ai/api/v1", api_key="k",
                      provider="openrouter", model="m", web_enabled=True)
    run_turn(req, repository=repo, tool_ctx=ctx,
             turn_fn=fake_turn, capability_fn=lambda *a, **k: True)
    assert "search_web" not in seen["names"] and "fetch_url" not in seen["names"]


def test_web_enabled_threads_to_cli_config(setup, monkeypatch):
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})
    seen = {}

    def fake_cli_turn(*, config, **kwargs):
        seen["config"] = config
        return "cli answer"

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", fake_cli_turn)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="",
                      api_key=None, provider="claude", model="sonnet",
                      web_enabled=True)
    run_turn(req, repository=repo, tool_ctx=ctx)
    assert seen["config"].web_enabled is True


def test_cli_config_carries_system_prompt_and_skill_block(setup):
    repo, ctx = setup
    captured = {}

    def fake_cli(*, messages, config, session_id, prior_session_id, repository, emit, **_):
        captured["config"] = config
        return "answer"

    request = TurnRequest(session_id="s1", text="/explain-score security",
                          ui_state=None, api_base="", api_key=None,
                          provider="claude", model="sonnet")
    run_turn(request, repository=repo, tool_ctx=ctx, cli_turn_fn=fake_cli)
    cfg = captured["config"]
    assert "# Active skill: explain-score" in cfg.system_prompt
    assert cfg.skill_block.startswith("[skill:explain-score]\n")


def test_cli_config_skill_block_empty_without_skill(setup):
    repo, ctx = setup
    captured = {}

    def fake_cli(*, messages, config, session_id, prior_session_id, repository, emit, **_):
        captured["config"] = config
        return "answer"

    request = TurnRequest(session_id="s1", text="hello",
                          ui_state=None, api_base="", api_key=None,
                          provider="claude", model="sonnet")
    run_turn(request, repository=repo, tool_ctx=ctx, cli_turn_fn=fake_cli)
    assert captured["config"].skill_block == ""
    assert captured["config"].system_prompt  # context always present


def test_skill_turns_get_extra_iterations(setup):
    repo, ctx = setup
    captured = {}

    def fake_api(*, messages, config, registry, emit, **_):
        captured["config"] = config
        return "ok"

    request = TurnRequest(session_id="s1", text="/explain-score security",
                          ui_state=None, api_base="http://x", api_key=None,
                          provider="ollama", model="m")
    run_turn(request, repository=repo, tool_ctx=ctx, turn_fn=fake_api)
    assert captured["config"].max_tool_iterations == 12

    request = TurnRequest(session_id="s1", text="hello", ui_state=None,
                          api_base="http://x", api_key=None,
                          provider="ollama", model="m")
    run_turn(request, repository=repo, tool_ctx=ctx, turn_fn=fake_api)
    assert captured["config"].max_tool_iterations == 6


# ---- stop-turn cancellation -------------------------------------------------

def test_cancelled_cli_turn_emits_stopped_and_persists_partial(setup, monkeypatch):
    from quodeq.assistant.cancel import TurnCancelled
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})

    def cancelled_cli_turn(**kwargs):
        raise TurnCancelled("partial answer")

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", cancelled_cli_turn)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="", api_key=None,
                      provider="claude", model="sonnet")
    run_turn(req, repository=repo, tool_ctx=ctx)
    msgs = repo.list_messages("s1")
    # the partial answer the user watched stream must survive in the history
    assert (msgs[-1]["role"], msgs[-1]["content"]) == ("assistant", "partial answer")
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "stopped"
    assert not any(f["type"] == "error" for f in frames)


def test_cancelled_turn_without_partial_persists_no_assistant_message(setup):
    from quodeq.assistant.cancel import TurnCancelled
    repo, ctx = setup

    def cancelled_turn(**_):
        raise TurnCancelled("")

    run_turn(_request(), repository=repo, tool_ctx=ctx, turn_fn=cancelled_turn,
             capability_fn=lambda *a, **k: True)
    assert [m["role"] for m in repo.list_messages("s1")] == ["user"]
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "stopped"


def test_run_turn_threads_cancel_token_to_adapter(setup):
    from quodeq.assistant.cancel import CancelToken
    repo, ctx = setup
    seen = {}

    def fake_turn(*, cancel, **_):
        seen["default"] = cancel
        return "hi"

    run_turn(_request(), repository=repo, tool_ctx=ctx, turn_fn=fake_turn,
             capability_fn=lambda *a, **k: True)
    assert isinstance(seen["default"], CancelToken)

    token = CancelToken()

    def fake_turn2(*, cancel, **_):
        seen["explicit"] = cancel
        return "hi"

    run_turn(_request(), repository=repo, tool_ctx=ctx, turn_fn=fake_turn2,
             capability_fn=lambda *a, **k: True, cancel=token)
    assert seen["explicit"] is token


def test_mcp_args_carry_read_only_and_cache_override(tmp_path):
    from quodeq.assistant import AssistantRepository
    from quodeq.assistant.orchestrator import TurnRequest, _mcp_server_args
    from quodeq.assistant.tools import ToolContext
    ctx = ToolContext(
        repository=AssistantRepository(tmp_path / "assistant.db"),
        session_id="s", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path, compiled_dir=tmp_path,
        dimensions_file=tmp_path / "dims.json",
        read_only=True, score_cache_path=tmp_path / "score_cache.db")
    req = TurnRequest(session_id="s", text="hi", ui_state=None, api_base="",
                      api_key=None, provider="claude", model="m")
    args = _mcp_server_args(req, ctx)
    assert "--read-only" in args
    assert "--score-cache-override" in args
    assert str(tmp_path / "score_cache.db") in args
