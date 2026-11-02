"""What a Claude scan may touch: its repo, the standards checklist and the findings tools."""
from __future__ import annotations

from quodeq.analysis.subprocess import AnalysisConfig, build_ai_cmd


def _claude_args(tmp_path):
    config = AnalysisConfig(
        ai_cmd="claude", ai_model="sonnet-4",
        jsonl_file=tmp_path / "evidence" / "security_evidence.jsonl",
        compiled_dir=tmp_path, dimension="security",
    )
    args, _ = build_ai_cmd("Analyze", config)
    return args


def test_shipped_claude_config_ignores_the_repo_settings(tmp_path):
    # The analysed repo's .claude/settings.json can define hooks, which run
    # shell commands that no permission mode stops: only user settings load.
    args = _claude_args(tmp_path)
    assert args[args.index("--setting-sources") + 1] == "user"
    assert args[args.index("--permission-mode") + 1] == "dontAsk"


def test_claude_gets_the_checklist_from_the_findings_server_not_a_path(tmp_path):
    # The checklist sits outside the repo; no Read rule may reach past the cwd.
    args = _claude_args(tmp_path)
    rules = args[args.index("--allowedTools") + 1].split(",")
    assert "mcp__findings__get_standards" in rules
    assert [r for r in rules if r.startswith("Read(")] == ["Read(./**)"]


def test_bedrock_credentials_pass_only_when_claude_uses_bedrock():
    from quodeq.analysis.subprocess import build_analysis_env

    env = {"AWS_ACCESS_KEY_ID": "a", "PATH": "/usr/bin"}
    assert "AWS_ACCESS_KEY_ID" not in build_analysis_env("claude", env=env)
    on = build_analysis_env("claude", env={**env, "CLAUDE_CODE_USE_BEDROCK": "1"})
    assert on.get("AWS_ACCESS_KEY_ID") == "a"
