"""Full loop for a CLI provider: create session -> message -> SSE frames -> apply.

Mirrors ``test_assistant_end_to_end.py`` (Plan 1, API providers) but drives a
CLI-provider ("claude") turn instead. No real CLI binary is ever spawned: the
`spawn_turn` boundary that `run_cli_turn` falls back to
(`quodeq.assistant.adapters._cli.spawn_turn`) is monkeypatched with a
`FakeProc` factory, the same seam already used by the unit tests in
`tests/assistant/test_cli_adapter.py`.

Provider "claude" is used deliberately: its catalog entry uses
`mcp_style: config-file`, so `run_cli_turn` only *writes* a temporary MCP
config JSON file for the (fake) CLI to read -- it never shells out to
`claude mcp add/remove` the way codex/gemini's registration-style MCP wiring
would. That keeps this test free of any real subprocess call.

Note on scope: in production, a *real* CLI process spawns the assistant MCP
server (`quodeq.assistant.mcp.server`) as its own child and talks to it over
stdio; that child dispatches `draft_action` against the shared
`AssistantRepository`, which is what produces the `action_draft` SSE frame.
Because the fake CLI here never spawns that child process, the fake
`spawn_fn` performs the equivalent dispatch itself (via the same
`build_registry`/`ToolRegistry.dispatch` code path the real MCP server uses)
so the test can assert the resulting `action_draft` frame. The genuine CLI
<-> MCP-server round trip (stdio JSON-RPC, tool discovery, live binary
quirks) is NOT exercised here -- it is covered only by the manual live smoke
test (Plan 2 Task 9 Step 5).

No `@pytest.mark.integration` marker, matching every other file already in
this directory (see the module docstring of `test_assistant_end_to_end.py`):
CI runs with `-m "not integration"`, which only deselects marked tests, so
this one still runs.
"""
import io
import json
import time
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

_STANDARD = {
    "id": "rfc7807-errors", "name": "RFC7807 Errors", "description": "d",
    "weight": 1.0, "source": "assistant",
    "principles": [{"name": "Errors", "description": "", "requirements": [
        {"id": "r1", "text": "Error bodies follow RFC7807", "description": "", "refs": []},
    ]}],
}


class FakeProc:
    """Stands in for a `subprocess.Popen` handle to a CLI binary."""

    def __init__(self, lines: list[str], returncode: int = 0):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.stderr = io.StringIO("")
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode


def _make_spawn_fn(app: Flask, holder: dict):
    """Fake CLI: dispatches `draft_action` for real (mirroring the MCP server's
    normal out-of-band role), then emits the scripted stream-json lines an
    actual CLI would print for a turn that called that tool.
    """

    def spawn_fn(argv, cwd, env):
        ctx = ToolContext(
            repository=AssistantRepository(app.config["ASSISTANT_DB_PATH"]),
            session_id=holder["session_id"],
            run_dir=None, repo_root=None,
            evaluators_dir=Path(app.config["STANDARDS_EVALUATORS_DIR"]),
            compiled_dir=Path(app.config["STANDARDS_COMPILED_DIR"]),
            dimensions_file=Path(app.config["STANDARDS_DIMENSIONS_FILE"]),
        )
        registry = build_registry(ctx)
        dispatched = registry.dispatch(
            "draft_action", {"action_type": "create_standard", "payload": _STANDARD})
        assert dispatched["ok"], dispatched

        lines = [
            json.dumps({"type": "system", "session_id": "fake-claude-session-1"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "c1", "name": "draft_action",
                 "input": {"action_type": "create_standard", "payload": _STANDARD}}]}}),
            json.dumps({"type": "result", "result": "Draft ready for review.",
                       "session_id": "fake-claude-session-1"}),
        ]
        return FakeProc(lines)

    return spawn_fn


@pytest.fixture()
def app(tmp_path, monkeypatch):
    holder: dict = {}
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        ASSISTANT_DB_PATH=str(tmp_path / "assistant.db"),
        STANDARDS_EVALUATORS_DIR=str(tmp_path / "evaluators"),
        STANDARDS_COMPILED_DIR=str(tmp_path / "compiled"),
        STANDARDS_DIMENSIONS_FILE=str(tmp_path / "dimensions.json"),
    )
    monkeypatch.setattr(
        "quodeq.assistant.adapters._cli.spawn_turn", _make_spawn_fn(app, holder))
    register_assistant_routes(app)
    app.extensions["_test_holder"] = holder
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_full_cli_draft_and_apply_flow(client, app, tmp_path):
    holder = app.extensions["_test_holder"]

    sid = client.post("/api/assistant/sessions",
                      json={"provider": "claude", "model": "sonnet"}).get_json()["sessionId"]
    holder["session_id"] = sid

    assert client.post(f"/api/assistant/sessions/{sid}/messages",
                       json={"text": "/create-standard RFC7807 error contract"},
                       ).status_code == 202

    # Poll events via a fresh AssistantRepository rather than re-fetching the
    # SSE stream body (see test_assistant_end_to_end.py for the rationale).
    repo = AssistantRepository(app.config["ASSISTANT_DB_PATH"])
    deadline = time.time() + 5
    events: list[dict] = []
    while time.time() < deadline:
        events = [frame for _seq, frame in repo.events_after(sid, 0)]
        if any(e.get("type") == "done" for e in events):
            break
        time.sleep(0.1)

    types = [e.get("type") for e in events]
    assert "action_draft" in types
    assert "done" in types

    draft_event = next(e for e in events if e.get("type") == "action_draft")
    action_id = draft_event["actionId"]
    assert client.post(f"/api/assistant/actions/{action_id}/apply").status_code == 200
    written = Path(tmp_path / "evaluators" / "rfc7807-errors.json")
    assert written.exists()
    assert json.loads(written.read_text())["name"] == "RFC7807 Errors"
