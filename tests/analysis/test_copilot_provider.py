import json
import subprocess
from unittest.mock import Mock

import pytest

from quodeq.analysis._command import _build_ai_cmd, _build_analysis_env
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.errors import FatalProviderError
from quodeq.analysis.stream.validation import get_mcp_status, is_stream_valid
from quodeq.analysis.subprocess import _run_cli_analysis
from quodeq.config.ai_provider import PROVIDERS
from quodeq.services.tooling_mixin import FsToolingMixin, get_allowed_client_ids

# The stream event Copilot emits when an org policy blocks the findings MCP
# server. Four tests drive the same event through different entry points.
POLICY_BLOCK_EVENT = {"type": "session.warning", "data": {
    "warningType": "mcp", "message": "1 MCP server was blocked by policy: 'findings'",
}}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))


def test_copilot_is_discoverable_and_keyless(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/bin/copilot" if name == "copilot" else None)
    clients = FsToolingMixin().get_ai_clients(env={})["clients"]
    assert {"id": "copilot", "label": "GitHub Copilot", "type": "cli", "installed": True} in clients
    assert "copilot" in get_allowed_client_ids(env={})
    assert PROVIDERS["copilot"] == ""


def test_copilot_model_listing_uses_account_discovery_not_interactive_cli(monkeypatch):
    run = Mock()
    monkeypatch.setattr("quodeq.services.tooling_mixin.run_cli_models_command", run)
    discover = Mock(return_value={"models": ["auto", "gpt-test"]})
    monkeypatch.setattr("quodeq.services.tooling_mixin.fetch_copilot_models", discover)
    assert FsToolingMixin().get_client_models("copilot") == {"models": ["auto", "gpt-test"]}
    discover.assert_called_once()
    run.assert_not_called()


@pytest.fixture()
def _built_ai_cmd(tmp_path):
    """Build the copilot CLI args + scoped MCP config file once; each test
    checks one slice of the result. Teardown removes the MCP config file
    regardless of test outcome."""
    config = AnalysisConfig(
        ai_cmd="copilot", ai_model="claude-sonnet-4.6",
        jsonl_file=tmp_path / "findings.jsonl", queue_path=tmp_path / "queue.json",
        agent_id="agent-2", max_turns=3, analysis_budget=1,
    )
    args, path = _build_ai_cmd("Inspect sources", config, work_dir=tmp_path)
    yield args, path
    if path:
        path.unlink(missing_ok=True)


def test_copilot_command_line_flags(_built_ai_cmd):
    args, path = _built_ai_cmd
    assert args[0] == "copilot"
    assert args[args.index("--output-format") + 1] == "json"
    assert args[args.index("--additional-mcp-config") + 1] == f"@{path}"
    assert args[args.index("--model") + 1] == "claude-sonnet-4.6"
    assert args[args.index("--allow-tool") + 1] == "findings"
    assert "--available-tools" in args
    assert all(tool in args for tool in ("view", "glob", "grep", "findings"))
    assert "--disable-builtin-mcps" in args
    assert "--no-custom-instructions" in args
    assert "Use view, glob and grep" in args[-1]


def test_copilot_forbidden_flags_are_absent(_built_ai_cmd):
    args, _path = _built_ai_cmd
    assert not {"--tools", "--strict-mcp-config", "--max-turns",
                "--max-budget-usd", "--allow-all-tools", "--yolo"} & set(args)


def test_copilot_scoped_mcp_json_exposes_only_the_findings_tool(_built_ai_cmd):
    _args, path = _built_ai_cmd
    payload = json.loads(path.read_text())
    server = payload["mcpServers"]["findings"]
    assert server["tools"] == ["*"]


def test_copilot_scoped_mcp_server_args_identify_the_agent_and_paths(_built_ai_cmd, tmp_path):
    _args, path = _built_ai_cmd
    payload = json.loads(path.read_text())
    server = payload["mcpServers"]["findings"]
    assert "agent-2" in server["args"]
    assert str(tmp_path / "queue.json") in server["args"]
    assert str(tmp_path.resolve()) in server["args"]


def test_copilot_analysis_env_uses_dedicated_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    env = _build_analysis_env("copilot", env={
        "PATH": "/bin", "COPILOT_HOME": "/personal-profile",
        "COPILOT_GITHUB_TOKEN": "not-inherited", "GH_TOKEN": "not-inherited",
        "GITHUB_TOKEN": "not-inherited", "COPILOT_ALLOW_ALL": "true",
        "COPILOT_PROVIDER_BASE_URL": "https://not-copilot.invalid",
    })
    assert env["COPILOT_HOME"] == str(tmp_path / ".quodeq" / "copilot")
    assert not {"GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN",
                "COPILOT_ALLOW_ALL", "COPILOT_PROVIDER_BASE_URL"} & env.keys()
    config = json.loads((tmp_path / ".quodeq/copilot/settings.json").read_text())
    assert config["disableAllHooks"] is True


def test_copilot_evaluation_uses_scratch_cwd_and_cleans_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    captured = {}

    def spawn(args, work_dir, env, paths, cfg):
        captured.update(args=args, cwd=work_dir, env=env)
        assert work_dir != tmp_path
        assert work_dir.is_dir()
        mcp = args[args.index("--additional-mcp-config") + 1]
        captured["mcp"] = mcp[1:]
        paths.stream_file.write_text('{"type":"result","exitCode":0}\n')
        return Mock(returncode=0), False

    monkeypatch.setattr("quodeq.analysis.subprocess._spawn_and_monitor", spawn)
    cfg = AnalysisConfig(ai_cmd="copilot", jsonl_file=tmp_path / "f.jsonl")
    _run_cli_analysis(tmp_path, "Inspect sources", tmp_path / "s.jsonl", cfg)
    from pathlib import Path
    assert not Path(captured["mcp"]).exists()
    assert not captured["cwd"].exists()
    args = captured["args"]
    assert args[args.index("--add-dir") + 1] == str(tmp_path)
    assert str(tmp_path) in args[-1]


def test_copilot_stdout_auth_error_aborts_evaluation(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    def spawn(args, work_dir, env, paths, cfg):
        paths.stream_file.write_text(json.dumps({
            "type": "session.error",
            "data": {"errorType": "authentication", "message": "Sign in to GitHub Copilot"},
        }) + "\n")
        return Mock(returncode=1), False

    monkeypatch.setattr("quodeq.analysis.subprocess._spawn_and_monitor", spawn)
    with pytest.raises(FatalProviderError, match="Sign in") as exc:
        _run_cli_analysis(tmp_path, "hi", tmp_path / "s.jsonl", AnalysisConfig(ai_cmd="copilot"))
    assert exc.value.reason == "auth"


@pytest.mark.parametrize("event", [
    {"type": "session.error", "data": {"message": "Model unavailable"}},
    {"type": "result", "exitCode": 1},
    POLICY_BLOCK_EVENT,
])
def test_copilot_error_stream_is_invalid(tmp_path, event):
    stream = tmp_path / "s.jsonl"
    stream.write_text(json.dumps(event))
    assert is_stream_valid(stream) is False


def test_copilot_mcp_status_after_initial_events(tmp_path):
    stream = tmp_path / "s.jsonl"
    stream.write_text('\n'.join(json.dumps(e) for e in [
        {"type": "session.info", "data": {}},
        {"type": "session.mcp_servers_loaded", "data": {
            "servers": [{"name": "findings", "status": "connected"}]}},
    ]))
    assert get_mcp_status(stream) == "connected"


@pytest.mark.parametrize("servers", [None, 42, "invalid", {"findings": "connected"},
                                     [{"name": "findings", "status": []}]])
def test_copilot_malformed_mcp_status_is_logged_and_skipped(tmp_path, servers):
    stream = tmp_path / "s.jsonl"
    stream.write_text('\n'.join(json.dumps(e) for e in [
        {"type": "session.mcp_servers_loaded", "data": {"servers": servers}},
        {"type": "session.mcp_servers_loaded", "data": {
            "servers": [{"name": "findings", "status": "connected"}]}},
    ]))
    log = Mock()
    assert get_mcp_status(stream, log=log) == "connected"
    log.debug.assert_called()


@pytest.mark.parametrize("with_callback", [False, True])
@pytest.mark.parametrize("prior_event", [None, {
    "type": "session.error", "data": {"message": "Transient provider failure"},
}])
def test_copilot_policy_block_terminates_running_evaluation(tmp_path, monkeypatch, with_callback, prior_event):
    from quodeq.analysis._process import _run_with_heartbeat

    stream = tmp_path / "s.jsonl"
    events = [prior_event, POLICY_BLOCK_EVENT] if prior_event else [POLICY_BLOCK_EVENT]
    stream.write_text("".join(json.dumps(event) + "\n" for event in events))
    process = Mock()
    process.poll.side_effect = [None, 0]
    process.wait.side_effect = subprocess.TimeoutExpired("copilot", 1)
    terminate = Mock()
    monkeypatch.setattr("quodeq.analysis._process._terminate_process", terminate)
    cfg = AnalysisConfig(ai_cmd="copilot", heartbeat_interval=1,
                         heartbeat_callback=Mock() if with_callback else None)
    with pytest.raises(FatalProviderError, match="administrator") as exc:
        _run_with_heartbeat(process, cfg, stream)
    assert exc.value.reason == "copilot_mcp_policy"
    terminate.assert_called_once_with(process)
    process.wait.assert_called_once_with(timeout=1)


def test_copilot_policy_block_cancels_pool_and_cleans_resources(tmp_path, monkeypatch):
    from pathlib import Path

    from quodeq.analysis.subagents._pool_scaling import should_respawn
    from quodeq.analysis.subagents._pool_worker import WorkerContext, run_single_agent
    from quodeq.shared import cancellation
    from tests._analysis_helpers import _FixedRemainingQueue

    captured = {}
    process = Mock()
    process.poll.side_effect = [None, 0]
    process.wait.side_effect = subprocess.TimeoutExpired("copilot", 1)

    def spawn(args, **kwargs):
        captured["cwd"] = Path(kwargs["cwd"])
        captured["mcp"] = Path(args[args.index("--additional-mcp-config") + 1][1:])
        kwargs["stdout"].write(json.dumps(POLICY_BLOCK_EVENT) + "\n")
        kwargs["stdout"].flush()
        return process

    monkeypatch.setattr("quodeq.analysis._process.subprocess.Popen", spawn)
    terminate = Mock()
    monkeypatch.setattr("quodeq.analysis._process._terminate_process", terminate)
    result = run_single_agent(
        0, tmp_path, "Inspect sources",
        AnalysisConfig(ai_cmd="copilot", heartbeat_interval=1),
        WorkerContext("security", "security", tmp_path, tmp_path / "queue.json"),
    )
    assert not result.success
    assert "administrator" in result.error
    assert cancellation.cancel_reason().startswith("provider_fatal:copilot_mcp_policy:")
    assert should_respawn(_FixedRemainingQueue(211), tmp_path / "queue.json", 0.0, 0) == 0
    terminate.assert_called_once_with(process)
    assert not captured["cwd"].exists()
    assert not captured["mcp"].exists()
    process.wait.assert_called_once_with(timeout=1)


def test_copilot_policy_block_in_completed_stream_aborts_evaluation(tmp_path, monkeypatch):
    def spawn(args, work_dir, env, paths, cfg):
        paths.stream_file.write_text(json.dumps(POLICY_BLOCK_EVENT) + "\n")
        return Mock(returncode=0), False

    monkeypatch.setattr("quodeq.analysis.subprocess._spawn_and_monitor", spawn)
    with pytest.raises(FatalProviderError, match="administrator") as exc:
        _run_cli_analysis(tmp_path, "hi", tmp_path / "s.jsonl", AnalysisConfig(ai_cmd="copilot"))
    assert exc.value.reason == "copilot_mcp_policy"
