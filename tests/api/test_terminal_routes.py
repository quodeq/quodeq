import contextlib
import threading
import time

import pytest
from flask import Flask

from quodeq.api.terminal_routes import _apply_control, register_terminal_routes

try:
    import simple_websocket
    from werkzeug.serving import make_server
    _WS_OK = True
except Exception:  # pragma: no cover - env without WS deps
    _WS_OK = False

_ws_test = pytest.mark.skipif(not _WS_OK, reason="simple_websocket/werkzeug unavailable")


class _FakeManager:
    def __init__(self):
        self.killed = False; self._alive = False; self.ensured = None
    def ensure_session(self, *, cwd, cols, rows): self._alive = True; self.ensured = (cwd, cols, rows)
    def scrollback(self): return b"hi\n"
    def read(self, max_bytes=65536): return b""
    def write(self, data): pass
    def resize(self, cols, rows): pass
    def kill(self): self.killed = True; self._alive = False
    @property
    def alive(self): return self._alive


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    register_terminal_routes(app, manager=_FakeManager())
    return app


def test_status_allowed_on_loopback(app):
    c = app.test_client()
    r = c.get("/api/terminal/status", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    assert r.get_json()["enabled"] is True


def test_status_enabled_without_origin_header(app):
    # Regression: /status is a same-origin GET and browsers omit the Origin
    # header on those. It must report enabled (env gate only), NOT refuse with
    # "Missing Origin header" — that bug made the terminal appear broken on mac.
    c = app.test_client()
    r = c.get("/api/terminal/status", base_url="http://localhost")  # no Origin
    assert r.status_code == 200
    body = r.get_json()
    assert body["enabled"] is True and body["reason"] is None


def test_status_refused_with_api_key(app):
    app.config["QUODEQ_API_KEY"] = "secret"
    c = app.test_client()
    r = c.get("/api/terminal/status", base_url="http://localhost")
    body = r.get_json()
    assert body["enabled"] is False and body["reason"]


def test_kill_refused_when_gated(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 403


def test_kill_ok_on_loopback(app):
    manager = app.extensions["terminal_manager"]
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    assert manager.killed is True


class _ResizeRecorder:
    def __init__(self):
        self.calls = []
    def resize(self, cols, rows):
        self.calls.append((cols, rows))


def test_apply_control_valid_resize_calls_manager():
    mgr = _ResizeRecorder()
    _apply_control(mgr, '{"resize":{"cols":100,"rows":40}}')
    assert mgr.calls == [(100, 40)]


@pytest.mark.parametrize("payload", [
    "not json",
    "{}",
    '{"resize":{"cols":"x"}}',
    '{"resize":123}',
])
def test_apply_control_malformed_is_noop_and_never_raises(payload):
    mgr = _ResizeRecorder()
    _apply_control(mgr, payload)  # must not raise
    assert mgr.calls == []


@pytest.mark.parametrize("payload", [
    '{"resize":{"cols":999999,"rows":40}}',   # > 65535 (struct.pack H overflow)
    '{"resize":{"cols":-5,"rows":40}}',        # negative
    '{"resize":{"cols":80,"rows":9999999}}',   # rows out of range
])
def test_apply_control_clamps_out_of_range_resize(payload):
    mgr = _ResizeRecorder()
    _apply_control(mgr, payload)  # must not raise (clamped, not dropped)
    assert len(mgr.calls) == 1
    cols, rows = mgr.calls[0]
    assert 1 <= cols <= 65535
    assert 1 <= rows <= 65535


# --- WebSocket integration (single-connection guard + spawn-failure handling) ---

class _LiveManager:
    """Stays alive; scrollback is a sync beacon proving the handler holds the lock."""
    def __init__(self):
        self._alive = True
    def ensure_session(self, *, cwd, cols, rows): self._alive = True
    def scrollback(self): return b"ready\n"
    def read(self, max_bytes=65536): time.sleep(0.05); return b""
    def write(self, data): pass
    def resize(self, cols, rows): pass
    def kill(self): self._alive = False
    @property
    def alive(self): return self._alive


class _FlakyManager(_LiveManager):
    """Raises on the first ensure_session (spawn failure), succeeds afterwards."""
    def __init__(self):
        super().__init__()
        self._calls = 0
    def ensure_session(self, *, cwd, cols, rows):
        self._calls += 1
        if self._calls == 1:
            raise RuntimeError("boom: shell spawn failed")
        self._alive = True


@contextlib.contextmanager
def _serve(manager):
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    register_terminal_routes(app, manager=manager)
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_port
    finally:
        srv.shutdown()
        t.join(timeout=2)


@contextlib.contextmanager
def _connect(port):
    # werkzeug's WS handshake exposes request.host without the port, so the
    # Origin must match that (browsers keep Host+Origin consistent for real).
    c = simple_websocket.Client(
        f"ws://127.0.0.1:{port}/api/terminal/ws",
        headers={"Origin": "http://127.0.0.1"})
    try:
        yield c
    finally:
        with contextlib.suppress(Exception):  # already-closed socket -> ignore
            c.close()


@_ws_test
def test_ws_single_active_connection_refuses_second():
    with _serve(_LiveManager()) as port:
        with _connect(port) as a:
            assert a.receive(timeout=2) == "0ready\n"   # A acquired the conn lock
            with _connect(port) as b:
                msg = None
                with contextlib.suppress(simple_websocket.ConnectionClosed):
                    msg = b.receive(timeout=2)
                assert msg is not None and "already open" in msg


@_ws_test
def test_ws_busy_close_uses_dedicated_code():
    # The client must NOT auto-reconnect against a held lock (it would ping-pong
    # and spam the other window), so the refusal carries close code 4002.
    with _serve(_LiveManager()) as port:
        with _connect(port) as a:
            assert a.receive(timeout=2) == "0ready\n"
            with _connect(port) as b:
                with pytest.raises(simple_websocket.ConnectionClosed) as exc:
                    b.receive(timeout=2)   # banner frame...
                    b.receive(timeout=2)   # ...then the close
                assert exc.value.reason == 4002


@_ws_test
def test_ws_gate_refusal_close_uses_dedicated_code():
    # Bad Origin -> gate refuses the handshake with close code 4003 so the
    # client reports it instead of retrying forever.
    with _serve(_LiveManager()) as port:
        c = simple_websocket.Client(
            f"ws://127.0.0.1:{port}/api/terminal/ws",
            headers={"Origin": "http://evil.example"})
        try:
            with pytest.raises(simple_websocket.ConnectionClosed) as exc:
                c.receive(timeout=2)
            assert exc.value.reason == 4003
        finally:
            with contextlib.suppress(Exception):
                c.close()


@_ws_test
def test_ws_spawn_failure_closes_cleanly_and_frees_lock():
    with _serve(_FlakyManager()) as port:
        with _connect(port) as first:       # ensure_session raises -> clean close
            with contextlib.suppress(simple_websocket.ConnectionClosed):
                first.receive(timeout=2)    # must not hang / must not 500
        # the conn lock's finally released even though spawn failed -> reattach works
        with _connect(port) as second:
            assert second.receive(timeout=2) == "0ready\n"
