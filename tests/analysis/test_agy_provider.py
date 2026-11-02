"""Antigravity CLI (agy) as a scan provider: its command line, permissions and cwd."""
import json
from unittest.mock import Mock

import pytest

from quodeq.analysis.stream.parser import extract_evidence_from_stream
from quodeq.analysis.stream.validation import denied_actions, is_stream_valid
from quodeq.analysis.subprocess import AnalysisConfig, build_ai_cmd, run_analysis
from quodeq.config.ai_provider import PROVIDERS
from quodeq.services.tooling_mixin import FsToolingMixin, get_allowed_client_ids


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture()
def agy_args(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = AnalysisConfig(
        ai_cmd="agy", ai_model="gemini-3.8-flash-high", ai_effort="high",
        jsonl_file=tmp_path / "findings.jsonl", queue_path=tmp_path / "queue.json",
    )
    args, path = build_ai_cmd("Inspect sources", config, work_dir=repo)
    assert path is None  # registered with `agy mcp add`, no per-run config file
    return args, repo


def _settings(args):
    return json.loads(args[args.index("--settings") + 1])


def test_agy_is_discoverable_and_keyless(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/bin/agy" if name == "agy" else None)
    clients = FsToolingMixin().get_ai_clients(env={})["clients"]
    assert {"id": "agy", "label": "Antigravity", "type": "cli", "installed": True} in clients
    assert "agy" in get_allowed_client_ids(env={})
    assert PROVIDERS["agy"] == ""


def test_agy_models_come_from_agy_models(monkeypatch):
    run = Mock(return_value="gemini-3.8-flash-high\tGemini 3.8 Flash (High)\nclaude-sonnet-4-6\tClaude\n")
    monkeypatch.setattr("quodeq.services.tooling_mixin.run_cli_models_command", run)
    assert FsToolingMixin().get_client_models("agy") == {
        "models": ["gemini-3.8-flash-high", "claude-sonnet-4-6"]}
    assert run.call_args.kwargs["args"] == ("models",)


def test_agy_headless_stream_json_with_model_and_effort(agy_args):
    args, _repo = agy_args
    assert args[0] == "agy"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--disable-slash-commands" in args
    assert args[args.index("--model") + 1] == "gemini-3.8-flash-high"
    assert args[args.index("--effort") + 1] == "high"
    assert args[-2] == "-p"


def test_agy_never_runs_with_auto_approval(agy_args):
    args, _repo = agy_args
    assert not {"--dangerously-skip-permissions", "--yolo", "--add-dir", "--sandbox"} & set(args)
    assert _settings(args)["toolPermission"] == "strict"


def test_agy_pre_approves_only_findings_tools_and_repo_reads(agy_args):
    args, repo = agy_args
    allow = _settings(args)["permissions"]["allow"]
    assert allow == ["mcp(quodeq-findings/*)", f"read_file({repo.resolve()})"]


def test_agy_denies_commands_writes_urls_and_browser(agy_args):
    args, _repo = agy_args
    deny = _settings(args)["permissions"]["deny"]
    assert {"command(*)", "write_file(/)", "read_url(*)", "execute_url(*)", "browser(*)"} <= set(deny)
    assert not any(rule.startswith("read_file") for rule in deny)  # deny beats allow in agy


def test_agy_prompt_names_the_repo_root(agy_args):
    args, repo = agy_args
    assert args[-1].startswith(f"Repository root: {repo.resolve()}\n")
    assert args[-1].endswith("Inspect sources")


def test_agy_runs_outside_the_repo(tmp_path, monkeypatch):
    """The repo's .agents/ hooks and plugin MCP servers load from agy's cwd."""
    captured = {}

    def spawn(args, work_dir, env, paths, cfg):
        captured.update(cwd=work_dir, cwd_existed=work_dir.is_dir())
        paths.stream_file.write_text('{"event":"result","result":{"status":"SUCCESS","response":"done"}}\n')
        return Mock(returncode=0), False

    monkeypatch.setattr("quodeq.analysis.subprocess.spawn_and_monitor", spawn)
    monkeypatch.setattr("quodeq.analysis.subprocess.confine_cli", lambda c, p, w, args, e, pol: (args, lambda: None))
    registry = Mock()
    cfg = AnalysisConfig(ai_cmd="agy", jsonl_file=tmp_path / "f.jsonl", mcp_registry=registry)
    run_analysis(tmp_path, "Inspect sources", tmp_path / "s.jsonl", cfg, env={})
    registry.ensure_registered.assert_called_once()
    assert captured["cwd_existed"] and not captured["cwd"].is_relative_to(tmp_path)
    assert not captured["cwd"].exists()


def _write(path, *events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


def test_agy_result_text_feeds_evidence_and_reads_count(tmp_path):
    finding = json.dumps({"p": "a.py", "t": "violation"})
    stream = _write(
        tmp_path / "s.jsonl",
        {"event": "step_update", "step_update": {
            "step_index": 2, "state": "ACTIVE", "step_type": "tool", "tool_name": "read_file",
            "tool_info": {"name": "read_file", "parameters": {"Path": "/repo/a.py"}}}},
        {"event": "result", "result": {"status": "SUCCESS", "response": finding}},
    )
    assert extract_evidence_from_stream(stream, tmp_path / "out.jsonl") == 1
    assert (tmp_path / "out.jsonl").read_text() == finding + "\n"
    assert is_stream_valid(stream)


def test_agy_failed_turn_and_refused_actions_are_reported(tmp_path):
    stream = _write(tmp_path / "s.jsonl", {"event": "result", "result": {
        "status": "ERROR", "response": "", "denied_actions": [{"action": "read_file"}]}})
    assert not is_stream_valid(stream)
    assert denied_actions(stream) == ["read_file"]
