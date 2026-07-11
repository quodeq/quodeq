from quodeq.assistant.adapters._cli_config import load_cli_chat_config


def test_claude_chat_config():
    cfg = load_cli_chat_config("claude")
    assert cfg.cmd == "claude"
    assert "--disallowedTools" in cfg.assistant_args
    # never the analysis bypass flag
    assert "bypassPermissions" not in cfg.assistant_args
    # plan mode blocks all MCP tool calls; it must be gone
    assert "--permission-mode" not in cfg.assistant_args
    # the scoped read-only MCP server is auto-approved so its tools can run
    assert "--allowedTools" in cfg.assistant_args
    i = cfg.assistant_args.index("--allowedTools")
    assert cfg.assistant_args[i + 1] == "mcp__quodeq-assistant"
    assert cfg.resume_style == "flag-resume"
    assert cfg.session_id_source == "preassign"


def test_codex_chat_config_is_mcp_only_externally_sandboxed():
    cfg = load_cli_chat_config("codex")
    # exec is supplied by cmd_subcommand, not assistant_args (no duplicate exec token)
    assert "exec" not in cfg.assistant_args
    assert "--json" in cfg.assistant_args
    assert "--skip-git-repo-check" in cfg.assistant_args
    # codex cancels MCP tool calls under its OWN sandbox, so it runs bypassed but
    # (1) with the shell tool + web search removed and (2) wrapped in an OS sandbox
    # we control (requires_external_sandbox) that blocks writes.
    assert "--dangerously-bypass-approvals-and-sandbox" in cfg.assistant_args
    i = cfg.assistant_args.index("--disable")
    assert cfg.assistant_args[i + 1] == "shell_tool"
    assert "tools.web_search=false" in cfg.assistant_args
    assert "-s" not in cfg.assistant_args  # codex's own sandbox is bypassed
    assert cfg.requires_external_sandbox is True
    assert cfg.resume_style == "exec-resume"
    assert cfg.session_id_source == "parse-jsonl"


def test_claude_and_gemini_do_not_require_external_sandbox():
    assert load_cli_chat_config("claude").requires_external_sandbox is False
    assert load_cli_chat_config("gemini").requires_external_sandbox is False


def test_gemini_chat_config_scopes_mcp():
    cfg = load_cli_chat_config("gemini")
    assert "--yolo" not in cfg.assistant_args
    assert "--approval-mode" in cfg.assistant_args
    assert "quodeq-assistant" in cfg.assistant_args
    assert cfg.resume_style == "gemini-resume"


def test_unknown_provider_raises():
    import pytest
    with pytest.raises(KeyError):
        load_cli_chat_config("nope")


def test_claude_system_prompt_style_is_argv_append():
    assert load_cli_chat_config("claude").system_prompt_style == "argv-append"


def test_codex_and_gemini_use_message_prefix():
    assert load_cli_chat_config("codex").system_prompt_style == "message-prefix"
    assert load_cli_chat_config("gemini").system_prompt_style == "message-prefix"
