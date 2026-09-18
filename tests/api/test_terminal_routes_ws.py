"""WebSocket integration tests for /api/terminal/ws: per-session connection guard and spawn failures."""
import contextlib
import threading
import time

import pytest
from flask import Flask

from quodeq.api.terminal_routes import register_terminal_routes
from quodeq.terminal.sessions import TerminalSessionRegistry
from tests._timeouts import budget


try:
    import simple_websocket
    from werkzeug.serving import make_server
    _WS_OK = True
except Exception:  # pragma: no cover - env without WS deps
    _WS_OK = False

_ws_test = pytest.mark.skipif(not _WS_OK, reason="simple_websocket/werkzeug unavailable")


# --- WebSocket integration (per-session connection guard + spawn-failure handling) ---

class _LiveManager:
    """Stays alive; scrollback is a sync beacon proving the handler holds the lock."""
    def __init__(self):
        self._alive = True
    def ensure_session(self, *, cwd, cols, rows): self._alive = True
    def scrollback(self): return "ready\n"
    def read(self, max_bytes=65536): time.sleep(0.05); return ""
    def write(self, data): pass
    def resize(self, cols, rows): pass
    def kill(self): self._alive = False
    @property
    def alive(self): return self._alive
    @property
    def pid(self): return None


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
def _serve(manager_factory):
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    registry = TerminalSessionRegistry(manager_factory=manager_factory)
    register_terminal_routes(app, registry=registry)
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv.server_port, registry
    finally:
        srv.shutdown()
        t.join(timeout=budget(2))


@contextlib.contextmanager
def _connect(port, session=None):
    # werkzeug's WS handshake exposes request.host without the port, so the
    # Origin must match that (browsers keep Host+Origin consistent for real).
    url = f"ws://127.0.0.1:{port}/api/terminal/ws"
    if session is not None:
        url += f"?session={session}"
    c = _Client(url, headers={"Origin": "http://127.0.0.1"})
    try:
        yield c
    finally:
        with contextlib.suppress(Exception):  # already-closed socket -> ignore
            c.close()


# Receive timeouts are upper bounds, not waits: generous so a CPU-starved
# server thread (full-suite load) can't turn a passing test into a flake.
_RECV_TIMEOUT = 10


if _WS_OK:
    class _Client(simple_websocket.Client):
        """Work around a simple-websocket (<= 1.1.0) client handshake bug.

        Client.handshake() feeds recv'd bytes to wsproto but consumes only the
        first event (AcceptConnection). Our server sends scrollback (and maybe
        a close) microseconds after the 101, so under suite load those frames
        coalesce into the same recv: their events stay queued inside wsproto
        while the reader thread blocks on recv() for bytes that never come,
        and receive() times out — the flake this suite used to have.
        """
        def handshake(self):
            super().handshake()
            # Drain events queued during the handshake. Safe: the reader
            # thread only starts after handshake() returns. A drained server
            # close sets connected=False, which would make Base.__init__
            # raise — undo that and let the reader thread see EOF instead;
            # close_reason is already recorded for ConnectionClosed.
            self._handle_events()
            self.connected = True


@_ws_test
def test_ws_single_active_connection_refuses_second_same_session():
    with _serve(_LiveManager) as (port, _):
        with _connect(port) as a:      # no id -> default session
            assert a.receive(timeout=budget(_RECV_TIMEOUT)) == "0ready\n"   # A acquired the conn lock
            with _connect(port) as b:  # no id -> SAME default session
                msg = None
                with contextlib.suppress(simple_websocket.ConnectionClosed):
                    msg = b.receive(timeout=budget(_RECV_TIMEOUT))
                assert msg is not None and "already open" in msg


@_ws_test
def test_ws_busy_close_uses_dedicated_code():
    # The client must NOT auto-reconnect against a held lock (it would ping-pong
    # and spam the other window), so the refusal carries close code 4002.
    with _serve(_LiveManager) as (port, _):
        with _connect(port) as a:
            assert a.receive(timeout=budget(2)) == "0ready\n"
            with _connect(port) as b:
                with pytest.raises(simple_websocket.ConnectionClosed) as exc:
                    b.receive(timeout=budget(2))   # banner frame...
                    b.receive(timeout=budget(2))   # ...then the close
                assert exc.value.reason == 4002


@_ws_test
def test_ws_two_sessions_stream_concurrently():
    # The busy lock is per session: a client on session A must not block a
    # client on session B.
    with _serve(_LiveManager) as (port, registry):
        sa = registry.create(); sb = registry.create()
        with _connect(port, session=sa.id) as a:
            assert a.receive(timeout=budget(_RECV_TIMEOUT)) == "0ready\n"
            with _connect(port, session=sb.id) as b:
                assert b.receive(timeout=budget(_RECV_TIMEOUT)) == "0ready\n"


@_ws_test
def test_ws_unknown_session_closes_with_not_found_code():
    # Stale tab id (server restarted): close 4004 tells the client to reconcile
    # via /sessions instead of retrying the dead URL.
    with _serve(_LiveManager) as (port, _):
        with _connect(port, session="deadbeef") as c:
            with pytest.raises(simple_websocket.ConnectionClosed) as exc:
                c.receive(timeout=budget(2))
            assert exc.value.reason == 4004


@_ws_test
def test_ws_gate_refusal_close_uses_dedicated_code():
    # Bad Origin -> gate refuses the handshake with close code 4003 so the
    # client reports it instead of retrying forever.
    with _serve(_LiveManager) as (port, _):
        c = simple_websocket.Client(
            f"ws://127.0.0.1:{port}/api/terminal/ws",
            headers={"Origin": "http://evil.example"})
        try:
            with pytest.raises(simple_websocket.ConnectionClosed) as exc:
                c.receive(timeout=budget(2))
            assert exc.value.reason == 4003
        finally:
            with contextlib.suppress(Exception):
                c.close()


@_ws_test
def test_ws_spawn_failure_closes_cleanly_and_frees_lock():
    with _serve(_FlakyManager) as (port, _):
        with _connect(port) as first:       # ensure_session raises -> clean close
            # The client must see why, not just a dropped connection: this is
            # sent "0"-prefixed (data), same as the "already open" banner
            # above, so the frontend actually renders it in the pane.
            msg = first.receive(timeout=budget(_RECV_TIMEOUT))
            assert msg is not None and "could not be started" in msg
            with contextlib.suppress(simple_websocket.ConnectionClosed):
                first.receive(timeout=budget(_RECV_TIMEOUT))    # then the close; must not hang / must not 500
        # the conn lock's finally released even though spawn failed -> reattach works
        with _connect(port) as second:
            assert second.receive(timeout=budget(_RECV_TIMEOUT)) == "0ready\n"
