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


def test_create_session_rejects_unknown_provider(client):
    assert client.post("/api/assistant/sessions", json={"provider": "nope"}).status_code == 400


def test_create_session_accepts_cli_provider(client):
    resp = client.post("/api/assistant/sessions", json={"provider": "claude", "model": "sonnet"})
    assert resp.status_code == 201
    assert resp.get_json()["sessionId"]


def test_cli_provider_not_busy_gated(client, app, monkeypatch):
    # even with a running job, a CLI provider session accepts a message (no single-slot contention)
    monkeypatch.setattr("quodeq.api._assistant_helpers.local_provider_busy", lambda p: False)
    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", lambda *a, **k: None)
    sid = client.post("/api/assistant/sessions", json={"provider": "claude"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
    assert resp.status_code == 202


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


def test_events_stream_heartbeats_while_idle(client, monkeypatch):
    # No message ever posted -> no rows to replay. With small _POLL_SECONDS/
    # _IDLE_LIMIT the stream must emit repeated ":keepalive" comments (not
    # just the one at open) instead of hanging until the idle limit, proving
    # event_frames yields a heartbeat sentinel on each idle tick.
    monkeypatch.setattr("quodeq.api._assistant_helpers._POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers._IDLE_LIMIT", 5)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    stream = client.get(f"/api/assistant/sessions/{sid}/events?after=0")
    body = stream.get_data(as_text=True)
    assert body.count(":keepalive") >= 2


def test_events_stream_emits_heartbeat_data_frame_on_sustained_idle(client, monkeypatch):
    # A slow local model can go 60s+ without a data frame. EventSource ignores
    # ":keepalive" SSE comments, so the browser's inactivity timer never
    # resets on comments alone. The generator must also emit a real
    # {"type": "heartbeat"} DATA frame on a throttled cadence (every 20th
    # idle tick == ~5s at the real _POLL_SECONDS) so the client sees liveness,
    # while a final "done" frame still terminates the stream normally.
    monkeypatch.setattr("quodeq.api._assistant_helpers._POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers._IDLE_LIMIT", 100)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    stream = client.get(f"/api/assistant/sessions/{sid}/events?after=0")
    body = stream.get_data(as_text=True)
    assert '"type": "heartbeat"' in body
    assert body.count(":keepalive") >= 2


def test_idle_limit_is_a_600s_safety_cap_not_a_60s_timeout():
    # A legitimate turn (cold-loading local 26B model, or a CLI provider near
    # its ~500s read timeout) can run minutes without a done/error frame yet
    # still be alive. run_turn always writes a terminal done/error frame on
    # completion, so event_frames already exits correctly then; _IDLE_LIMIT
    # only guards against a turn that dies without ever emitting one (e.g. a
    # crashed daemon thread), so it must be generous, not a tight timeout.
    from quodeq.api import _assistant_helpers
    assert _assistant_helpers._IDLE_LIMIT == 2400


def test_post_message_unknown_session_404(client):
    assert client.post("/api/assistant/sessions/nope/messages",
                       json={"text": "x"}).status_code == 404


def test_local_provider_ignores_request_api_base(client, app, monkeypatch):
    captured = {}

    def fake_run_turn(request, *, repository, tool_ctx, **kw):
        captured["api_base"] = request.api_base
        captured["api_key"] = request.api_key
        repository.append_event(request.session_id, {"type": "done"})

    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", fake_run_turn)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    resp = client.post(
        f"/api/assistant/sessions/{sid}/messages",
        json={"text": "hello", "apiBase": "http://evil.internal/v1", "apiKey": "leaked"},
    )
    assert resp.status_code == 202
    time.sleep(0.3)
    assert captured["api_base"] == "http://localhost:11434/v1"
    assert captured["api_key"] is None


def test_create_session_resolves_run_from_project_and_run_id(client, app, monkeypatch, tmp_path):
    # a resolver stub standing in for the real services lookup
    run_dir = tmp_path / "proj-uuid" / "run-9"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.resolve_run_location",
        lambda project_id, run_id: (str(run_dir), "/src/selectives-android"),
    )
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "selectives", "runId": "run-9"})
    assert resp.status_code == 201
    sid = resp.get_json()["sessionId"]
    from quodeq.data.sqlite.assistant_repository import AssistantRepository
    sess = AssistantRepository(app.config["ASSISTANT_DB_PATH"]).get_session(sid)
    assert sess["run_id"] == str(run_dir)
    assert sess["project_uuid"] == "/src/selectives-android"


def test_explicit_rundir_still_wins(client, monkeypatch):
    monkeypatch.setattr("quodeq.api._assistant_helpers.resolve_run_location",
                        lambda *a: (_ for _ in ()).throw(AssertionError("should not resolve")))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "runDir": "/explicit/run", "repoRoot": "/explicit/repo"})
    assert resp.status_code == 201


def test_resolve_run_location_rejects_path_traversal(monkeypatch, tmp_path):
    # Evaluations root with a real run inside it, plus a sibling dir OUTSIDE
    # the root that a "../.." project id could otherwise reach.
    evals = tmp_path / "evaluations"
    (evals / "proj" / "run-1").mkdir(parents=True)
    outside = tmp_path / "outside" / "run-1"
    outside.mkdir(parents=True)
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.get_evaluations_dir", lambda: str(evals)
    )
    from quodeq.api._assistant_helpers import resolve_run_location
    # A traversal project id that would escape the root must NOT resolve, even
    # though the escaped target ("../outside/run-1") exists on disk.
    assert resolve_run_location("../outside", "run-1") == (None, None)
    assert resolve_run_location("../..", "outside") == (None, None)
    # Sanity: a legit project id still resolves inside the root.
    run_dir, _ = resolve_run_location("proj", "run-1")
    assert run_dir == str((evals / "proj" / "run-1").resolve())


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
