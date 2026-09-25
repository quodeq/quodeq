"""Assistant message turns: run_turn dispatch, request scrubbing and the SSE event stream."""
import time

from tests._timeouts import budget
from tests.api._assistant_routes_fixtures import (  # noqa: F401 -- app/client are pytest fixtures
    _repo,
    app,
    client,
)


def test_cli_provider_not_busy_gated(client, app, monkeypatch):
    # even with a running job, a CLI provider session accepts a message (no single-slot contention)
    monkeypatch.setattr("quodeq.api._assistant_helpers.local_provider_busy", lambda p: False)
    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", lambda *a, **k: None)
    sid = client.post("/api/assistant/sessions", json={"provider": "claude"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
    assert resp.status_code == 202


def test_post_message_spawns_turn_and_streams(client, app, monkeypatch):
    # The stream now stays open past a turn's `done` (so 2nd+ turns still
    # reach the browser), so bound the idle backstop to keep this consuming
    # test from blocking the full 600s window once the turn's frames drain.
    monkeypatch.setattr("quodeq.api._assistant_helpers.POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers.IDLE_LIMIT", 30)

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


def test_event_frames_keeps_yielding_past_a_done_frame(app, monkeypatch):
    # Regression for the 2nd-turn hang: event_frames must NOT terminate on a
    # `done` frame. A turn's done is a marker, not the end of the stream — an
    # event appended AFTER a done (i.e. the next turn) must still be yielded so
    # one SSE connection serves the whole session.
    monkeypatch.setattr("quodeq.api._assistant_helpers.POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers.IDLE_LIMIT", 40)
    from quodeq.api._assistant_helpers import event_frames

    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    # Turn 1: a token then a done marker.
    repo.append_event("s1", {"type": "token", "text": "A"})
    repo.append_event("s1", {"type": "done"})

    gen = event_frames(repo, "s1", 0)
    frames = []
    # Drain turn 1 (skipping heartbeat sentinels), then append turn 2's frames
    # and confirm the SAME generator delivers them — proving it did not stop
    # on the first done.
    appended_turn2 = False
    for item in gen:
        if item is None:
            if not appended_turn2:
                repo.append_event("s1", {"type": "token", "text": "B"})
                repo.append_event("s1", {"type": "done"})
                appended_turn2 = True
            continue
        _seq, frame = item
        frames.append(frame)
        # Stop once we've seen turn 2's content delivered past turn 1's done.
        if frame.get("type") == "token" and frame.get("text") == "B":
            break

    types_texts = [(f.get("type"), f.get("text")) for f in frames]
    assert ("token", "A") in types_texts
    # A done was yielded (turn marker) but did NOT terminate the generator...
    assert ("done", None) in types_texts
    # ...because turn 2's token, appended AFTER that done, still arrived.
    assert ("token", "B") in types_texts


def test_events_stream_heartbeats_while_idle(client, monkeypatch):
    # No message ever posted -> no rows to replay. With small POLL_SECONDS/
    # IDLE_LIMIT the stream must emit repeated ":keepalive" comments (not
    # just the one at open) instead of hanging until the idle limit, proving
    # event_frames yields a heartbeat sentinel on each idle tick.
    monkeypatch.setattr("quodeq.api._assistant_helpers.POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers.IDLE_LIMIT", 5)
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
    # idle tick == ~5s at the real POLL_SECONDS) so the client sees liveness,
    # while a final "done" frame still terminates the stream normally.
    monkeypatch.setattr("quodeq.api._assistant_helpers.POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers.IDLE_LIMIT", 100)
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
    # completion, so event_frames already exits correctly then; IDLE_LIMIT
    # only guards against a turn that dies without ever emitting one (e.g. a
    # crashed daemon thread), so it must be generous, not a tight timeout.
    from quodeq.api import _assistant_helpers
    assert _assistant_helpers.IDLE_LIMIT == 2400


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


def test_non_fixed_provider_also_ignores_request_api_base(client, app, monkeypatch):
    # SSRF guard: even a genuinely caller-defined provider (custom/openrouter)
    # must take api_base from the SERVER catalog, never the request body, so a
    # request can't redirect the turn's HTTP at an internal host.
    catalog = {"openrouter": {"type": "api", "api_base": "https://openrouter.ai/api/v1"}}
    monkeypatch.setattr("quodeq.api.assistant_routes.get_provider_configs", lambda: catalog)
    captured = {}

    def fake_run_turn(request, *, repository, tool_ctx, **kw):
        captured["api_base"] = request.api_base
        repository.append_event(request.session_id, {"type": "done"})

    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", fake_run_turn)
    monkeypatch.setattr("quodeq.api._assistant_helpers.local_provider_busy", lambda p: False)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "openrouter", "model": "m"}).get_json()["sessionId"]
    resp = client.post(
        f"/api/assistant/sessions/{sid}/messages",
        json={"text": "hi", "apiBase": "http://169.254.169.254/latest/meta-data/"},
    )
    assert resp.status_code == 202
    time.sleep(0.3)
    assert captured["api_base"] == "https://openrouter.ai/api/v1"


def _wait_for(seen, key, timeout=2.0):
    deadline = time.time() + budget(timeout)
    while key not in seen and time.time() < deadline:
        time.sleep(0.01)
    return seen.get(key)


def test_web_enabled_body_key_threads_to_turn_request(client, monkeypatch):
    seen = {}
    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn",
                        lambda turn, **kw: seen.setdefault("turn", turn))
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages",
                       json={"text": "hi", "webEnabled": True})
    assert resp.status_code == 202
    turn = _wait_for(seen, "turn")
    assert turn is not None and turn.web_enabled is True


def test_web_enabled_defaults_false_when_absent(client, monkeypatch):
    seen = {}
    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn",
                        lambda turn, **kw: seen.setdefault("turn", turn))
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama"}).get_json()["sessionId"]
    client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
    turn = _wait_for(seen, "turn")
    assert turn is not None and turn.web_enabled is False


def test_message_passes_write_enabled(client, app, monkeypatch):
    import threading
    seen = {}
    done = threading.Event()
    monkeypatch.setattr("quodeq.api._assistant_helpers.local_provider_busy",
                        lambda p: False)

    def fake_run_turn(turn, **kw):
        seen["write_enabled"] = turn.write_enabled
        done.set()
    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", fake_run_turn)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama"}).get_json()["sessionId"]
    client.post(f"/api/assistant/sessions/{sid}/messages",
                json={"text": "hi", "writeEnabled": True})
    assert done.wait(timeout=budget(2))  # run_turn runs on a daemon thread
    assert seen.get("write_enabled") is True


def test_post_message_non_object_body_has_code(client):  # 2532
    sid = client.post("/api/assistant/sessions", json={"provider": "claude"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/messages", json=[1])
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["code"] == "INVALID_PARAM"
