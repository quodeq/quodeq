"""Full loop: create session → message → SSE frames → draft card → apply.

No live services are involved (the LLM client is monkeypatched at the
`_default_client` boundary), so this test deliberately carries NO
`@pytest.mark.integration` marker — matching every other file already in
this directory (test_cancel_resume.py, test_sse_run_events_e2e.py, etc.),
none of which are marked either. CI runs with `-m "not integration"`, which
only deselects marked tests, so this one still runs.
"""
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.data.sqlite.assistant_repository import AssistantRepository

_STANDARD = {
    "id": "rfc7807-errors", "name": "RFC7807 Errors", "description": "d",
    "weight": 1.0, "source": "assistant",
    "principles": [{"name": "Errors", "description": "", "requirements": [
        {"id": "r1", "text": "Error bodies follow RFC7807", "description": "", "refs": []},
    ]}],
}


def _delta(content=None, tool_calls=None, finish=None):
    d = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=d, finish_reason=finish)])


def _tc(index, call_id, name, args):
    return SimpleNamespace(index=index, id=call_id,
                           function=SimpleNamespace(name=name, arguments=args))


class ScriptedClient:
    def __init__(self):
        args = json.dumps({"action_type": "create_standard", "payload": _STANDARD})
        self._scripts = [
            [_delta(tool_calls=[_tc(0, "c1", "draft_action", args)]),
             _delta(finish="tool_calls")],
            [_delta("Draft ready for review."), _delta(finish="stop")],
        ]
        completions = SimpleNamespace(create=lambda **kw: iter(self._scripts.pop(0)))
        self.chat = SimpleNamespace(completions=completions)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def app(tmp_path, monkeypatch):
    # NOTE: real get_provider_configs() returns dict[str, dict] keyed by
    # provider id (see src/quodeq/analysis/_provider_cache.py and
    # src/quodeq/data/config/ai_providers.json), not {"providers": [...]}
    # as an earlier draft of this test assumed. Mirrors the fixture in
    # tests/api/test_assistant_routes.py.
    monkeypatch.setattr(
        "quodeq.api.assistant_routes.get_provider_configs",
        lambda: {"ollama": {"type": "api",
                            "api_base": "http://localhost:11434/v1",
                            "model": "qwen3"}},
    )
    monkeypatch.setattr(
        "quodeq.assistant.orchestrator.supports_native_tools",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "quodeq.assistant.adapters._api._default_client",
        lambda config: ScriptedClient(),
    )
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        ASSISTANT_DB_PATH=str(tmp_path / "assistant.db"),
        STANDARDS_EVALUATORS_DIR=str(tmp_path / "evaluators"),
        STANDARDS_COMPILED_DIR=str(tmp_path / "compiled"),
        STANDARDS_DIMENSIONS_FILE=str(tmp_path / "dimensions.json"),
    )
    register_assistant_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_full_draft_and_apply_flow(client, app, tmp_path):
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "qwen3"}).get_json()["sessionId"]
    assert client.post(f"/api/assistant/sessions/{sid}/messages",
                       json={"text": "/create-standard RFC7807 error contract"},
                       ).status_code == 202

    # Poll events via a fresh AssistantRepository rather than re-fetching the
    # SSE stream body: doing so avoids flakiness where the streamed response
    # is consumed only once and repeated GETs against a live generator
    # interact poorly with the Flask test client under a polling loop.
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
