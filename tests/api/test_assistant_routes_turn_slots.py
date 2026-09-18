"""Assistant turn-slot lifecycle: setup failures, stop, SSE stream caps and shared-session 409s."""
import time

import pytest

from tests._timeouts import budget
from tests.api._assistant_routes_fixtures import (  # noqa: F401 -- app/client are pytest fixtures
    _repo,
    app,
    client,
)


def test_turn_lock_is_freed_when_setup_raises(client, app, monkeypatch):
    # If build_tool_context (or anything else between the lock `add` and the
    # worker thread starting) raises, the session's slot must still be freed
    # -- otherwise every future POST to this session 409s forever.
    calls = {"n": 0}

    def _boom(*_a, **_kw):
        calls["n"] += 1
        raise RuntimeError("setup exploded")

    monkeypatch.setattr("quodeq.api.assistant_routes.build_tool_context", _boom)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]

    # TESTING=True propagates unhandled exceptions to the test client instead
    # of converting them to a 500 response -- assert the exception surfaces
    # (mirroring the real 500 a caller would get), not a canned status code.
    with pytest.raises(RuntimeError, match="setup exploded"):
        client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
    assert calls["n"] == 1

    # The slot must have been freed -- a second POST must NOT see a stale 409.
    with pytest.raises(RuntimeError, match="setup exploded"):
        client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi again"})
    assert calls["n"] == 2


# ---- stop-turn endpoint -----------------------------------------------------

def test_stop_unknown_session_404(client):
    assert client.post("/api/assistant/sessions/nope/stop").status_code == 404


def test_stop_without_running_turn_409(client):
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/stop")
    assert resp.status_code == 409


def test_stop_cancels_running_turn_and_frees_the_token(client, monkeypatch):
    import threading
    started, finished = threading.Event(), threading.Event()

    def fake_run_turn(request, *, repository, tool_ctx, cancel, **kw):
        started.set()
        assert cancel.wait(timeout=budget(5))  # blocks until the stop route cancels
        finished.set()

    monkeypatch.setattr("quodeq.api.assistant_routes.run_turn", fake_run_turn)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    assert client.post(f"/api/assistant/sessions/{sid}/messages",
                       json={"text": "hi"}).status_code == 202
    assert started.wait(timeout=budget(5))

    resp = client.post(f"/api/assistant/sessions/{sid}/stop")
    assert resp.status_code == 202
    assert resp.get_json() == {"stopping": True}
    assert finished.wait(timeout=budget(5))

    # once the worker unwinds, the token is gone: a second stop has nothing to
    # cancel, and a new message can claim the turn slot again
    deadline = time.time() + budget(5)
    while time.time() < deadline:
        if client.post(f"/api/assistant/sessions/{sid}/stop").status_code == 409:
            break
        time.sleep(0.01)
    else:
        pytest.fail("cancel token not cleaned up after the turn ended")

    # The slot is reclaimable. Reap the turn this starts before returning:
    # fake_run_turn parks the worker until something cancels it, so a thread
    # left running here outlives the test, and once monkeypatch unwinds its
    # assert fires inside whichever test happens to be running 5s later
    # (it surfaced as a PytestUnhandledThreadExceptionWarning attributed to
    # test_shared_session_resolves_clone_run_dir on an unrelated xdist worker).
    started.clear()
    finished.clear()
    assert client.post(f"/api/assistant/sessions/{sid}/messages",
                       json={"text": "again"}).status_code == 202
    assert started.wait(timeout=budget(5))
    assert client.post(f"/api/assistant/sessions/{sid}/stop").status_code == 202
    assert finished.wait(timeout=budget(5))


# ---------------------------------------------------------------------------
# SEC-00 -- each open SSE stream pins a worker thread and GETs bypass the
# global rate limiter, so the events endpoint caps concurrently open streams.
# ---------------------------------------------------------------------------

def test_events_stream_returns_429_above_cap(app, client):
    state = app.extensions["assistant_turns"]

    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    slots_taken = 0
    while state.try_open_sse_stream():  # saturate this app's cap
        slots_taken += 1
    try:
        resp = client.get(f"/api/assistant/sessions/{sid}/events?after=0")
        assert resp.status_code == 429
        assert "error" in resp.get_json()
    finally:
        for _ in range(slots_taken):
            state.close_sse_stream()


def test_events_stream_releases_slot_when_stream_ends(app, client, monkeypatch):
    monkeypatch.setattr("quodeq.api._assistant_helpers._POLL_SECONDS", 0.001)
    monkeypatch.setattr("quodeq.api._assistant_helpers._IDLE_LIMIT", 5)
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama", "model": "m"}).get_json()["sessionId"]
    stream = client.get(f"/api/assistant/sessions/{sid}/events?after=0")
    assert stream.status_code == 200
    stream.get_data(as_text=True)  # drain to completion
    stream.close()
    assert app.extensions["assistant_turns"].open_sse_streams == 0


def test_events_stream_404_does_not_consume_slot(app, client):
    state = app.extensions["assistant_turns"]
    before = state.open_sse_streams
    resp = client.get("/api/assistant/sessions/nope/events?after=0")
    assert resp.status_code == 404
    assert state.open_sse_streams == before


def test_turn_state_instances_are_independent():
    """Two apps in one process (each with its own AssistantTurnState) must not
    share turn slots, cancel tokens, or SSE stream counts."""
    from quodeq.api.assistant_routes import AssistantTurnState

    a, b = AssistantTurnState(), AssistantTurnState()
    assert a.try_claim_turn("s1")
    assert not a.try_claim_turn("s1")
    assert b.try_claim_turn("s1")  # b has its own slot registry
    assert b.claim_turn("s2") is not None
    assert a.cancel_token("s2") is None  # token registered on b only
    a.release_turn("s1")
    assert not a.is_turn_claimed("s1")
    assert b.is_turn_claimed("s1")

    small = AssistantTurnState(max_sse_streams=1)
    assert small.try_open_sse_stream()
    assert not small.try_open_sse_stream()  # small's cap reached
    assert b.try_open_sse_stream()          # b's counter unaffected
    small.close_sse_stream()
    assert small.open_sse_streams == 0


def test_message_on_shared_session_without_repo_409s_and_frees_the_slot(client, app, monkeypatch):
    from quodeq.services.shared_settings import SharedSettings
    # The session was created while a shared repo was configured; it has
    # since been disconnected. build_tool_context must surface this as a
    # 409, and the running-turn slot must be released so the session is
    # not permanently locked out.
    _repo(app).create_session(session_id="s-gone", provider="ollama", source="shared")
    monkeypatch.setattr("quodeq.api._assistant_helpers.read_settings",
                        lambda: SharedSettings(url=None))
    first = client.post("/api/assistant/sessions/s-gone/messages", json={"text": "hi"})
    assert first.status_code == 409
    assert "shared repository" in first.get_json()["error"]
    # Slot freed: the next POST must hit the same 409, NOT "a turn is
    # already running".
    second = client.post("/api/assistant/sessions/s-gone/messages", json={"text": "hi"})
    assert second.status_code == 409
    assert "already running" not in second.get_json()["error"]


def test_message_on_shared_session_with_bad_clone_state_409s_and_frees_the_slot(client, app, monkeypatch):
    from quodeq.services.shared_settings import SharedSettings
    # The session was created while the shared clone was in a servable state;
    # a background refresh has since pulled a foreign/unsupported clone. The
    # route's pre-check (_shared_source_error, same helper the session-create
    # route uses) must surface this as a 409 before claiming the turn slot,
    # so the slot is never held and nothing needs releasing on this path.
    _repo(app).create_session(session_id="s-foreign", provider="ollama", source="shared")
    monkeypatch.setattr("quodeq.api.assistant_routes.read_settings",
                        lambda: SharedSettings(url="file:///tmp/fake.git"))
    monkeypatch.setattr("quodeq.api.assistant_routes.read_state", lambda url: "foreign")
    first = client.post("/api/assistant/sessions/s-foreign/messages", json={"text": "hi"})
    assert first.status_code == 409
    assert "foreign" in first.get_json()["error"]
    # Slot freed: the next POST must hit the same 409, NOT "a turn is
    # already running".
    second = client.post("/api/assistant/sessions/s-foreign/messages", json={"text": "hi"})
    assert second.status_code == 409
    assert "already running" not in second.get_json()["error"]
