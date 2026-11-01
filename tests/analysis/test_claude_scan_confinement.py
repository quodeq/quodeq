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


def test_claude_may_read_the_standards_checklist_outside_the_repo(tmp_path):
    # The prompt's first action reads <evidence>/.quodeq_standards_<dim>.md;
    # dontAsk denies it unless a rule names it, and the run finds nothing.
    args = _claude_args(tmp_path)
    rules = args[args.index("--allowedTools") + 1].split(",")
    assert f"Read(/{(tmp_path / 'evidence').resolve().as_posix()}/.quodeq_standards_*)" in rules
