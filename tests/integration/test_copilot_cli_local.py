"""Real Copilot CLI and MCP round trips, using only a synthetic localhost model.

Run explicitly with ``pytest tests/integration/test_copilot_cli_local.py``.
No GitHub login, model entitlement or external inference endpoint is used.
"""
import json
import shutil
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subprocess import run_analysis
from quodeq.assistant.adapters.cli import run_cli_turn
from quodeq.shared.copilot import build_copilot_env
from tests.assistant._cli_adapter_helpers import _config, _repo, _session

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not shutil.which("copilot"), reason="Copilot CLI not installed"),
    pytest.mark.timeout(90),
]


@pytest.fixture
def local_model(tmp_path, monkeypatch):
    calls = []
    tool = {"name": "", "arguments": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            messages = body["messages"]
            last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
            completed = sum(m["role"] == "tool" for m in messages[last_user + 1:])
            steps = tool.get("steps", [tool])
            if completed < len(steps):
                current = steps[completed]
                delta = {"role": "assistant", "tool_calls": [
                    {"index": 0, "id": f"call_{len(calls)}", "type": "function",
                     "function": {"name": current["name"], "arguments": json.dumps(current["arguments"])}}]}
                finish = "tool_calls"
            else:
                delta, finish = {"role": "assistant", "content": "Synthetic answer."}, "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in [
                {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            ]:
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    def offline_env(env):
        result = build_copilot_env(env)
        # Inject after production isolation, which intentionally strips BYOK.
        result.update(
            COPILOT_OFFLINE="true",
            COPILOT_PROVIDER_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
            COPILOT_PROVIDER_TYPE="openai",
            COPILOT_PROVIDER_WIRE_API="completions",
            COPILOT_PROVIDER_MODEL_ID="gpt-4.1",
            PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        )
        return result

    monkeypatch.setattr("quodeq.analysis._command.build_copilot_env", offline_env)
    monkeypatch.setattr("quodeq.assistant.adapters._cli_spawn.build_copilot_env", offline_env)
    try:
        yield calls, tool
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_copilot_evaluation_records_mcp_finding(tmp_path, local_model):
    calls, tool = local_model
    source = tmp_path / "sources"
    source.mkdir()
    (source / "example.py").write_text("def example():\n    return 1\n")
    findings = tmp_path / "findings.jsonl"
    stream = tmp_path / "stream.jsonl"
    tool.update(name="findings-report_finding", arguments={
        "req": "M-ANA-1", "p": "Analysability", "t": "compliance",
        "d": "maintainability", "file": "example.py", "line": 1,
        "severity": "minor", "w": "Synthetic finding", "reason": "Local protocol fixture",
    })
    tool["steps"] = [
        {"name": "view", "arguments": {"path": str(source / "example.py")}},
        {"name": tool["name"], "arguments": tool["arguments"]},
    ]
    run_analysis(source, "Report the synthetic fixture.", stream, AnalysisConfig(
        ai_cmd="copilot", ai_model="gpt-4.1", jsonl_file=findings,
        max_duration=60, heartbeat_interval=1,
    ))
    assert json.loads(findings.read_text().splitlines()[0])["w"] == "Synthetic finding"
    names = {t["function"]["name"] for t in calls[0]["tools"]}
    assert "findings-report_finding" in names
    assert names <= {"view", "glob", "grep", "findings-report_finding", "findings-mark_file_done",
                     "findings-get_next_files"}
    events = [json.loads(line) for line in stream.read_text().splitlines()]
    assert any(e["type"] == "tool.execution_complete" and e["data"]["success"] for e in events)
    assert len([e for e in events if e["type"] == "tool.execution_complete" and e["data"]["success"]]) == 2
    assert "def example()" in json.dumps(calls[1]["messages"])


@pytest.fixture
def _first_turn(tmp_path, local_model):
    """Run the first assistant CLI turn against the synthetic MCP model.
    Each test below checks one behaviour of that single turn; the resume
    test drives the second turn itself since it depends on this one's
    session id and call log."""
    calls, tool = local_model
    tool.update(name="quodeq-assistant-list_standards", arguments={})
    (tmp_path / "d.json").write_text('{"dimensions":[]}')
    repo = _repo(tmp_path)
    cfg = replace(_config(tmp_path), provider="copilot", model="gpt-4.1")
    for name in ("evaluators", "compiled"):
        (tmp_path / name).mkdir()
    cfg = replace(cfg, mcp_server_args=[
        "--db-path", str(cfg.db_path), "--session-id", "s1",
        "--evaluators-dir", str(tmp_path / "evaluators"),
        "--compiled-dir", str(tmp_path / "compiled"),
        "--dimensions-file", str(tmp_path / "d.json"),
    ])
    frames = []
    text = run_cli_turn(
        messages=[{"role": "user", "content": "List synthetic standards."}],
        config=cfg, session=_session(repo, emit=frames.append),
    )
    return repo, cfg, calls, text, frames


def test_first_turn_returns_the_synthetic_answer_and_streams_frames(_first_turn):
    _repo, _cfg, _calls, text, frames = _first_turn
    assert text == "Synthetic answer."
    assert [f["text"] for f in frames if f["type"] == "token"] == ["Synthetic answer."]
    assert any(f["type"] == "tool_call" and f["name"] == "list_standards" for f in frames)


def test_first_turn_tools_are_scoped_to_quodeq_assistant(_first_turn):
    _repo, _cfg, calls, _text, _frames = _first_turn
    names = {t["function"]["name"] for t in calls[0]["tools"]}
    assert names and all(name.startswith("quodeq-assistant-") for name in names)


def test_first_turn_tool_reply_confirms_ok(_first_turn):
    _repo, _cfg, calls, _text, _frames = _first_turn
    tool_reply = next(m for m in calls[1]["messages"] if m["role"] == "tool")
    assert json.loads(tool_reply["content"])["ok"] is True


def test_first_turn_persists_the_cli_session_id(_first_turn):
    repo, _cfg, _calls, _text, _frames = _first_turn
    assert repo.get_session("s1")["cli_session_id"]


def test_resume_continues_with_the_same_session_and_replays_context(_first_turn):
    repo, cfg, calls, text, _frames = _first_turn
    sid = repo.get_session("s1")["cli_session_id"]
    before = len(calls)
    resumed = run_cli_turn(
        messages=[{"role": "user", "content": "List synthetic standards."},
                  {"role": "assistant", "content": text},
                  {"role": "user", "content": "List them again."}],
        config=cfg, session=_session(repo, prior_session_id=sid),
    )
    assert resumed == "Synthetic answer."
    assert repo.get_session("s1")["cli_session_id"] == sid
    assert "Synthetic answer." in json.dumps(calls[before]["messages"])
