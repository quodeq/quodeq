from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec


def _echo_spec():
    return ToolSpec(
        name="echo",
        description="Echo the input",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=lambda text: {"echoed": text},
    )


def test_dispatch_success():
    reg = ToolRegistry()
    reg.register(_echo_spec())
    assert reg.dispatch("echo", {"text": "hi"}) == {"ok": True, "result": {"echoed": "hi"}}


def test_dispatch_unknown_tool():
    reg = ToolRegistry()
    out = reg.dispatch("nope", {})
    assert out["ok"] is False
    assert "unknown tool" in out["error"]


def test_dispatch_tool_error_and_bad_args():
    def boom():
        raise ToolError("no run selected")

    reg = ToolRegistry()
    reg.register(ToolSpec("boom", "always fails", {"type": "object", "properties": {}}, boom))
    assert reg.dispatch("boom", {}) == {"ok": False, "error": "no run selected"}
    assert reg.dispatch("boom", {"bogus": 1})["ok"] is False  # TypeError contained


def test_openai_tools_shape_and_duplicate_rejected():
    reg = ToolRegistry()
    reg.register(_echo_spec())
    (tool,) = reg.openai_tools()
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "echo"
    assert tool["function"]["parameters"]["required"] == ["text"]
    try:
        reg.register(_echo_spec())
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


from pathlib import Path

from quodeq.assistant import AssistantRepository
from quodeq.assistant.tools import ToolContext, build_registry


def _ctx(tmp_path, **kw):
    return ToolContext(
        repository=AssistantRepository(tmp_path / "assistant.db"),
        session_id="s", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path, compiled_dir=tmp_path,
        dimensions_file=tmp_path / "dims.json", **kw)


def test_read_only_registry_has_no_draft_action(tmp_path):
    names = {t["function"]["name"]
             for t in build_registry(_ctx(tmp_path, read_only=True)).openai_tools()}
    assert "draft_action" not in names
    assert {"get_scores", "get_violations", "get_overview", "get_context"} <= names


def test_default_registry_keeps_draft_action(tmp_path):
    names = {t["function"]["name"]
             for t in build_registry(_ctx(tmp_path)).openai_tools()}
    assert "draft_action" in names
