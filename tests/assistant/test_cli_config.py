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


def test_codex_chat_config_is_read_only():
    cfg = load_cli_chat_config("codex")
    # exec is supplied by cmd_subcommand, not assistant_args (no duplicate exec token)
    assert "exec" not in cfg.assistant_args
    assert "--json" in cfg.assistant_args
    assert "-s" in cfg.assistant_args and cfg.assistant_args[cfg.assistant_args.index("-s") + 1] == "read-only"
    assert "--skip-git-repo-check" in cfg.assistant_args
    assert "-a" not in cfg.assistant_args
    assert "--approval-mode" not in cfg.assistant_args
    assert "--dangerously-bypass-approvals-and-sandbox" not in cfg.assistant_args
    assert cfg.resume_style == "exec-resume"
    assert cfg.session_id_source == "parse-jsonl"


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
