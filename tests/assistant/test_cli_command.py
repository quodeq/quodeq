from quodeq.assistant.adapters._cli_command import build_turn_argv
from quodeq.assistant.adapters._cli_config import load_cli_chat_config


def _spec(provider, **kw):
    defaults = dict(prompt="hi", model="m", mcp_config_path=None,
                    prior_session_id=None, new_session_id="sid-1")
    defaults.update(kw)
    return build_turn_argv(load_cli_chat_config(provider), **defaults)


def test_claude_turn1_preassigns_session_id():
    spec = _spec("claude")
    assert spec.argv[0] == "claude"
    assert "--session-id" in spec.argv
    assert spec.argv[spec.argv.index("--session-id") + 1] == "sid-1"
    assert "--resume" not in spec.argv
    assert spec.argv[-2:] == ["-p", "hi"]  # prompt via flag, last
    assert spec.session_id == "sid-1"
    assert spec.needs_id_parse is False
    # hardened: no analysis bypass, tools disallowed present
    assert "bypassPermissions" not in spec.argv
    assert "--disallowedTools" in spec.argv


def test_claude_turnN_uses_resume():
    spec = _spec("claude", prior_session_id="old-sid")
    assert "--resume" in spec.argv
    assert spec.argv[spec.argv.index("--resume") + 1] == "old-sid"
    assert "--session-id" not in spec.argv


def test_claude_mcp_config_wired():
    spec = _spec("claude", mcp_config_path="/tmp/mcp.json")
    assert "--mcp-config" in spec.argv
    assert spec.argv[spec.argv.index("--mcp-config") + 1] == "/tmp/mcp.json"


def test_codex_turn1_parses_id_positional_prompt():
    spec = _spec("codex")
    assert spec.argv[0] == "codex"
    assert "exec" in spec.argv
    assert spec.argv[-1] == "hi"          # positional prompt
    assert spec.needs_id_parse is True
    assert spec.session_id is None


def test_codex_turnN_exec_resume():
    spec = _spec("codex", prior_session_id="th-1")
    assert spec.argv[:3] == ["codex", "exec", "resume"]
    assert "th-1" in spec.argv
    assert spec.argv[-1] == "hi"


def test_codex_turn1_full_argv():
    spec = _spec("codex")
    assert spec.argv == [
        "codex", "exec", "--json", "-s", "read-only", "-a", "never",
        "--model", "m", "hi",
    ]


def test_codex_turnN_full_argv():
    spec = _spec("codex", prior_session_id="th-1")
    assert spec.argv == [
        "codex", "exec", "resume", "th-1", "--json", "-s", "read-only",
        "-a", "never", "--model", "m", "hi",
    ]


def test_gemini_turn1_preassign_and_resume():
    spec1 = _spec("gemini")
    assert "--session-id" in spec1.argv and spec1.session_id == "sid-1"
    spec2 = _spec("gemini", prior_session_id="g-1")
    assert "-r" in spec2.argv and spec2.argv[spec2.argv.index("-r") + 1] == "g-1"


def test_claude_web_enabled_swaps_native_web_tools():
    spec = _spec("claude", web_enabled=True)
    disallowed = spec.argv[spec.argv.index("--disallowedTools") + 1]
    allowed = spec.argv[spec.argv.index("--allowedTools") + 1]
    assert disallowed == "Bash Edit Write NotebookEdit"
    assert allowed == "mcp__quodeq-assistant WebSearch WebFetch"


def test_claude_web_disabled_keeps_hardened_defaults():
    spec = _spec("claude")  # web_enabled defaults to False
    assert spec.argv[spec.argv.index("--allowedTools") + 1] == "mcp__quodeq-assistant"
    assert "WebFetch" in spec.argv[spec.argv.index("--disallowedTools") + 1]


def test_web_flag_is_inert_for_codex_and_gemini():
    assert _spec("codex", web_enabled=True).argv == _spec("codex").argv
    assert _spec("gemini", web_enabled=True).argv == _spec("gemini").argv
