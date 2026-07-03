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
