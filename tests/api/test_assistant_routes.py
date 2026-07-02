import json
import time

import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.data.sqlite.assistant_repository import AssistantRepository

_VALID_STANDARD = {
    "id": "api-errors", "name": "API Error Contract", "description": "d",
    "weight": 1.0, "source": "assistant",
    "principles": [{"name": "P1", "description": "", "requirements": [
        {"id": "r1", "text": "Endpoints return RFC7807", "description": "", "refs": []},
    ]}],
}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    # deterministic provider catalog for tests
    # NOTE: real get_provider_configs() (quodeq.llm_bridge / analysis._provider_cache)
    # returns dict[str, dict] keyed by provider id, not {"providers": [...]}.
    # See src/quodeq/analysis/_provider_cache.py:67 and
    # src/quodeq/data/config/ai_providers.json (top-level keys are provider ids).
    catalog = {
        "ollama": {"type": "api", "api_base": "http://localhost:11434/v1"},
        "claude": {"type": "cli"},
    }
    monkeypatch.setattr(
        "quodeq.api.assistant_routes.get_provider_configs", lambda: catalog
    )
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "assistant.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "evaluators")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "compiled")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "dimensions.json")
    register_assistant_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _repo(app):
    return AssistantRepository(app.config["ASSISTANT_DB_PATH"])


def test_create_session(client):
    resp = client.post("/api/assistant/sessions", json={"provider": "ollama", "model": "m"})
    assert resp.status_code == 201
    assert resp.get_json()["sessionId"]


def test_create_session_rejects_unknown_and_cli_provider(client):
    assert client.post("/api/assistant/sessions", json={"provider": "nope"}).status_code == 400
    assert client.post("/api/assistant/sessions", json={"provider": "claude"}).status_code == 400


def test_post_message_spawns_turn_and_streams(client, app, monkeypatch):
    def fake_run_turn(request, *, repository, tool_ctx, **kw):
        repository.add_message(request.session_id, "user", request.text)
        repository.append_event(request.session_id, {"type": "token", "text": "hi"})
        repository.append_event(request.session_id, {"type": "done"})

    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", fake_run_turn)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hello"})
    assert resp.status_code == 202
    time.sleep(0.3)  # let the daemon thread finish
    stream = client.get(f"/api/assistant/sessions/{sid}/events?after=0")
    body = stream.get_data(as_text=True)
    assert '"type": "token"' in body
    assert '"type": "done"' in body


def test_post_message_unknown_session_404(client):
    assert client.post("/api/assistant/sessions/nope/messages",
                       json={"text": "x"}).status_code == 404


def test_apply_action_creates_standard(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    resp = client.post("/api/assistant/actions/a1/apply")
    assert resp.status_code == 200
    assert repo.get_action("a1")["status"] == "applied"
    # standard file written by StandardsService
    import pathlib
    written = pathlib.Path(app.config["STANDARDS_EVALUATORS_DIR"]) / "api-errors.json"
    assert written.exists()
    assert json.loads(written.read_text())["name"] == "API Error Contract"


def test_apply_twice_conflicts(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    assert client.post("/api/assistant/actions/a1/apply").status_code == 200
    assert client.post("/api/assistant/actions/a1/apply").status_code == 409


def test_reject_action(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    resp = client.post("/api/assistant/actions/a1/reject")
    assert resp.status_code == 200
    assert repo.get_action("a1")["status"] == "rejected"


def test_apply_unknown_action_404(client):
    assert client.post("/api/assistant/actions/missing/apply").status_code == 404


def test_apply_invalid_payload_400(client, app):
    # A malformed stored draft (missing "principles") must yield a clean 400,
    # not a 500 — import_from_file raises ValueError on validation failure.
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    invalid = {k: v for k, v in _VALID_STANDARD.items() if k != "principles"}
    repo.create_action(action_id="a-bad", session_id="s1",
                       action_type="create_standard",
                       payload=invalid, content_hash="h")
    resp = client.post("/api/assistant/actions/a-bad/apply")
    assert resp.status_code == 400
    assert resp.get_json()["error"]
    assert repo.get_action("a-bad")["status"] == "drafted"
